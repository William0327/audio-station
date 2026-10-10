import asyncio
import json
import hashlib
import shutil
import sqlite3
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from controller import settings as s
from controller.voices import ConversionOptions

guard = threading.RLock()
shutdown = threading.Event()
upload_lock = asyncio.Lock()
transitions = {}
TERMINAL = {'completed', 'failed', 'cancelled'}

def now():
    return datetime.now(timezone.utc).isoformat()

def db():
    connection = sqlite3.connect(s.DATA / 'jobs.sqlite', timeout=10)
    connection.row_factory = sqlite3.Row
    return connection

def query(sql, args=(), one=False):
    with closing(db()) as connection, connection:
        cursor = connection.execute(sql, args)
        if cursor.description:
            rows = [dict(r) for r in cursor.fetchall()]
            return (rows[0] if rows else None) if one else rows

def job_or_404(id):
    row = query('SELECT * FROM jobs WHERE id=?', (id,), one=True)
    if not row:
        raise HTTPException(404, 'Job not found')
    return row

def gateway(method, path, **kwargs):
    if not s.TOKEN:
        raise HTTPException(503, 'Docker gateway is not configured; run the installer on your Linux workstation')
    try:
        with httpx.Client(timeout=httpx.Timeout(15, read=None if path in {'/separator/run','/applio/run','/applio/voices/import'} else 15)) as client:
            response = client.request(method, s.GATEWAY + path, headers={'X-Gateway-Token': s.TOKEN}, **kwargs)
        if response.is_error:
            try:
                detail = response.json().get('detail', 'Workload request failed')
            except ValueError:
                detail = 'Workload request failed'
            raise HTTPException(response.status_code, detail)
        return response.json()
    except httpx.HTTPError:
        raise HTTPException(503, 'Docker gateway unavailable; check host configuration')

def worker():
    # An interrupted Docker exec may outlive the controller. Stop it before accepting another job.
    interrupted = query("SELECT DISTINCT tool FROM jobs WHERE state='running'")
    while interrupted and not shutdown.is_set():
        try:
            for item in interrupted:
                gateway('POST', f"/services/{item['tool']}/stop")
                query("UPDATE jobs SET state='failed', error=?, finished=? WHERE state='running' AND tool=?",
                      ('Controller restarted during processing; workload stopped for recovery', now(), item['tool']))
            interrupted = []
        except HTTPException:
            shutdown.wait(5)
    while not shutdown.is_set():
        with guard:
            row = query("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1", one=True)
            if row:
                query("UPDATE jobs SET state='running', started=? WHERE id=?", (now(), row['id']))
        if not row:
            shutdown.wait(1)
            continue
        execution_attempted = False
        try:
            state = gateway('GET', f"/services/{row['tool']}")['state']
            if state != 'ready':
                raise HTTPException(409, f"{row['tool'].title()} must be ready before processing; start it and resubmit")
            execution_attempted = True
            payload = {k: row[k] for k in ('id','extension','model','format')}
            if row['tool'] == 'applio':
                payload['options'] = json.loads(row['options'])
            result = gateway('POST', f"/{row['tool']}/run", json=payload)
            if result['exit_code'] != 0:
                raise HTTPException(500, f"{row['tool'].title()} exited with code {result['exit_code']}; see process log")
            if not stem_files(row['id']):
                raise HTTPException(500, 'Workload produced no audio files; check mounted paths and log')
            with guard:
                query("UPDATE jobs SET state='completed', finished=? WHERE id=? AND state='running'", (now(), row['id']))
        except Exception as exc:
            message = str(exc.detail) if isinstance(exc, HTTPException) else 'Processing failed; inspect host logs'
            # A broken gateway connection does not prove that Docker exec exited.
            # Confirm a stop before dispatching more work, even across gateway restarts.
            if execution_attempted:
                stopped = False
                while not shutdown.is_set():
                    try:
                        gateway('POST', f"/services/{row['tool']}/stop")
                        stopped = True
                        break
                    except HTTPException:
                        shutdown.wait(5)
                if not stopped:
                    return  # Leave running metadata for startup recovery.
            with guard:
                query("UPDATE jobs SET state='failed', error=?, finished=? WHERE id=? AND state='running'", (message, now(), row['id']))

@asynccontextmanager
async def lifespan(app):
    for p in (s.DATA, s.INPUT, s.OUTPUT, s.MODELS):
        p.mkdir(parents=True, exist_ok=True)
    query('''CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, filename TEXT NOT NULL,
        extension TEXT NOT NULL, size INTEGER NOT NULL, model TEXT NOT NULL, format TEXT NOT NULL,
        state TEXT NOT NULL, created TEXT NOT NULL, started TEXT, finished TEXT, error TEXT)''')
    columns = {column['name'] for column in query('PRAGMA table_info(jobs)')}
    if 'tool' not in columns:
        query("ALTER TABLE jobs ADD COLUMN tool TEXT NOT NULL DEFAULT 'separator'")
    if 'options' not in columns:
        query("ALTER TABLE jobs ADD COLUMN options TEXT NOT NULL DEFAULT '{}'")
    shutdown.clear()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    yield
    shutdown.set()
    for item in query("SELECT DISTINCT tool FROM jobs WHERE state='running'"):
        try:
            await asyncio.to_thread(gateway, 'POST', f"/services/{item['tool']}/stop")
        except HTTPException:
            pass  # Startup recovery will retry before allowing another execution.
    await asyncio.to_thread(thread.join, 20)

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

@app.get('/api/setup')
def setup():
    return gateway('GET', '/setup')

@app.post('/api/tools/{service}/install', status_code=202)
def install_tool(service: str):
    if service not in {'separator', 'applio'}:
        raise HTTPException(404, 'Unknown service')
    return gateway('POST', f'/install/{service}')

@app.post('/api/models/{id}/install', status_code=202)
def install_model(id: str):
    from controller.catalog import CATALOG
    if id not in CATALOG:
        raise HTTPException(404, 'Unknown catalogue entry')
    return gateway('POST', f'/models/{id}/install')

@app.delete('/api/models/{id}', status_code=202)
def delete_model(id: str, confirm: bool = False):
    from controller.catalog import CATALOG
    if id not in CATALOG:
        raise HTTPException(404, 'Unknown catalogue entry')
    if not confirm:
        raise HTTPException(409, 'Confirm deletion of catalogue model files')
    return gateway('DELETE', f'/models/{id}?confirm=true')

@app.middleware('http')
async def same_origin(request: Request, call_next):
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('origin')
        expected = str(request.base_url).rstrip('/')
        if (origin and origin != expected) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Cross-origin requests are not allowed'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response

@app.get('/health')
def health():
    return {'ok': True}

@app.get('/api/services')
def services():
    result = {}
    for name in ('separator', 'applio'):
        try:
            info = gateway('GET', '/services/' + name)
        except HTTPException as exc:
            info = {'state': 'error', 'error': exc.detail}
        transition = transitions.get(name)
        if transition and time.monotonic() < transition[1]:
            if transition[0] == 'stopping' and info['state'] not in {'stopped', 'error'}:
                info['state'] = 'stopping'
            elif transition[0] == 'starting' and info['state'] == 'stopped':
                info['state'] = 'starting'
        if info['state'] == 'ready' and query("SELECT id FROM jobs WHERE state='running' AND tool=?", (name,)):
            info['state'] = 'busy'
        info['url'] = '/separator' if name == 'separator' else s.APPLIO_URL
        result[name] = info
    return result

@app.post('/api/services/{service}/start')
def start(service: str):
    if service not in {'separator', 'applio'}:
        raise HTTPException(404, 'Unknown service')
    with guard:
        transitions[service] = ('starting', time.monotonic() + 15)
        return gateway('POST', f'/services/{service}/start')

@app.post('/api/services/{service}/stop')
def stop(service: str, confirm: bool = False):
    if service not in {'separator', 'applio'}:
        raise HTTPException(404, 'Unknown service')
    with guard:
        active = query("SELECT id FROM jobs WHERE state IN ('running','queued') AND tool=?", (service,))
        if active and not confirm:
            raise HTTPException(409, 'Stopping cancels the running job and queued jobs. Confirm to continue.')
        transitions[service] = ('stopping', time.monotonic() + 30)
        result = gateway('POST', f'/services/{service}/stop')
        query("UPDATE jobs SET state='cancelled', finished=?, error='Workload stopped by user' WHERE state IN ('running','queued') AND tool=?", (now(), service))
        return result

@app.get('/api/system/gpu')
def gpu():
    try:
        return gateway('GET', '/gpu')
    except HTTPException as exc:
        return {'available': False, 'reason': exc.detail}

@app.get('/api/separator/models')
def models():
    from controller.catalog import CATALOG
    installed = s.installed_models()
    labels = {entry['model_filename']: entry['title'] for entry in CATALOG.values()
              if entry['tool'] == 'separator' and entry.get('model_filename') in installed}
    return {'models': installed, 'labels': labels}


@app.get('/api/applio/voices')
def voice_library():
    return gateway('GET', '/applio/voices')


@app.post('/api/applio/voices', status_code=201)
async def import_voice(request: Request, filename: str, confirm: bool = False):
    if not confirm:
        raise HTTPException(409, 'Confirm that you trust this voice model/index and have permission to use it. Models may execute code when loaded by Applio.')
    if s.DEPLOYMENT_MODE != 'managed':
        raise HTTPException(409, 'Voice imports require managed mode')
    filename = filename.replace('\\','/').split('/')[-1][:180]
    if Path(filename).suffix.lower() not in {'.pth','.index'} or filename.startswith(('.', 'G_', 'D_')):
        raise HTTPException(422, 'Import a .pth voice model or .index file; ZIP archives are not supported')
    id = uuid.uuid4().hex
    directory = s.contained(s.INPUT,'voice-imports',id)
    directory.mkdir(parents=True)
    size = 0
    digest = hashlib.sha256()
    try:
        with (directory/'asset').open('xb') as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > s.MAX_VOICE_IMPORT:
                    raise HTTPException(413, 'Voice asset exceeds import limit')
                digest.update(chunk)
                await asyncio.to_thread(handle.write,chunk)
        if not size:
            raise HTTPException(422, 'Voice file is empty')
        return await asyncio.to_thread(gateway,'POST','/applio/voices/import',json={
            'id':id,'filename':filename,'size':size,'sha256':digest.hexdigest()})
    finally:
        shutil.rmtree(directory,ignore_errors=True)


@app.post('/api/applio/jobs', status_code=201)
async def submit_conversion(request: Request, filename: str, model: str, format: str = 'WAV',
                            index: str = '', pitch: int = 0, index_rate: float = 0.75,
                            protect: float = 0.33, volume_envelope: float = 1,
                            f0_method: str = 'rmvpe'):
    from pydantic import ValidationError
    try:
        options = ConversionOptions(index=index,pitch=pitch,index_rate=index_rate,protect=protect,
                                    volume_envelope=volume_envelope,f0_method=f0_method)
    except ValidationError:
        raise HTTPException(422, 'Invalid conversion settings')
    library = await asyncio.to_thread(gateway,'GET','/applio/voices')
    if model not in {item['id'] for item in library['models']} or (index and index not in {item['id'] for item in library['indexes']}):
        raise HTTPException(422, 'Choose an installed voice model/index')
    return await submit_audio(request,filename,model,format,'applio',options.model_dump())

@app.post('/api/separator/jobs', status_code=201)
async def submit(request: Request, filename: str, model: str, format: str = 'WAV'):
    return await submit_audio(request, filename, model, format)


async def submit_audio(request, filename, model, format, tool='separator', options=None):
    # Raw request streaming enforces the limit before multipart can spool an oversized file.
    filename = filename.replace('\\', '/').split('/')[-1][:180]
    extension = Path(filename).suffix.lower()
    if extension not in s.EXTENSIONS or (tool == 'separator' and model not in s.installed_models()) or format not in {'WAV', 'MP3', 'FLAC'}:
        raise HTTPException(422, 'Choose a supported audio file, installed model, and output format')
    serialized_options = json.dumps(options or {}, sort_keys=True)
    key = request.headers.get('idempotency-key', '')
    if not 8 <= len(key) <= 128:
        raise HTTPException(422, 'A stable Idempotency-Key of 8–128 characters is required')
    async with upload_lock:
        previous = await asyncio.to_thread(query, 'SELECT * FROM jobs WHERE request_key=?', (key,), True)
        if previous:
            if (previous['filename'],previous['model'],previous['format'],previous['tool'],previous['options']) != (filename,model,format,tool,serialized_options):
                raise HTTPException(409, 'Idempotency key already used for a different submission')
            return previous
        id = uuid.uuid4().hex
        directory = s.contained(s.INPUT, id)
        directory.mkdir()
        output_directory = s.contained(s.OUTPUT, id)
        size = 0
        try:
            with (directory / ('source' + extension)).open('wb') as handle:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > s.MAX_UPLOAD:
                        raise HTTPException(413, f'File exceeds {s.MAX_UPLOAD // 1024 // 1024} MB limit')
                    await asyncio.to_thread(handle.write, chunk)
            if size == 0:
                raise HTTPException(422, 'Audio file is empty')
            output_directory.mkdir()
            if s.DEPLOYMENT_MODE == 'managed':
                # Controller UID 10001 / GID 0 and the gateway share this group.
                # No gateway DAC_OVERRIDE/CHOWN capability is needed.
                output_directory.chmod(0o770)
            with guard:
                await asyncio.to_thread(query, 'INSERT INTO jobs (id,request_key,filename,extension,size,model,format,state,created,tool,options) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                                        (id, key, filename, extension, size, model, format, 'queued', now(), tool, serialized_options))
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            shutil.rmtree(output_directory, ignore_errors=True)
            raise
    return job_or_404(id)

@app.get('/api/jobs')
def jobs():
    return query('SELECT * FROM jobs ORDER BY created DESC LIMIT 200')

@app.get('/api/jobs/{id}')
def get_job(id: str):
    return job_or_404(id)

@app.post('/api/jobs/{id}/cancel')
def cancel(id: str):
    with guard:
        row = job_or_404(id)
        if row['state'] == 'running':
            # Stopping the approved container terminates the entire inference process tree.
            gateway('POST', f"/services/{row['tool']}/stop")
            query("UPDATE jobs SET state='cancelled', finished=?, error='Cancelled; workload stopped to release resources' WHERE state IN ('running','queued') AND tool=?", (now(),row['tool']))
        elif row['state'] == 'queued':
            query("UPDATE jobs SET state='cancelled', finished=? WHERE id=?", (now(), id))
    return job_or_404(id)

def stem_files(id):
    directory = s.contained(s.OUTPUT, id)
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in s.EXTENSIONS)

@app.get('/api/jobs/{id}/results')
def results(id: str):
    row = job_or_404(id)
    files = stem_files(id) if row['state'] == 'completed' else []
    from urllib.parse import quote
    return [{'name': p.name, 'size': p.stat().st_size, 'url': f'/api/jobs/{id}/files/{quote(p.name)}'} for p in files]

@app.get('/api/jobs/{id}/files/{filename}')
def download(id: str, filename: str):
    if job_or_404(id)['state'] != 'completed':
        raise HTTPException(409, 'Job has not completed')
    path = next((p for p in stem_files(id) if p.name == filename), None)
    if not path:
        raise HTTPException(404, 'Stem not found')
    return FileResponse(path, filename=path.name, content_disposition_type='inline')

@app.get('/api/jobs/{id}/zip')
def download_zip(id: str):
    with guard:
        if job_or_404(id)['state'] != 'completed':
            raise HTTPException(409, 'Job has not completed')
        path = s.contained(s.OUTPUT, id, 'stems.zip')
        if not path.exists():
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
                for file in stem_files(id):
                    archive.write(file, file.name)
        return FileResponse(path, filename=f'stems-{id[:8]}.zip')

@app.get('/api/jobs/{id}/log')
def log(id: str):
    job_or_404(id)
    path = s.contained(s.OUTPUT, id, 'process.log')
    if not path.is_file() or path.is_symlink():
        return {'text': 'No process log yet.'}
    with path.open('rb') as handle:
        handle.seek(max(0, path.stat().st_size - 32000))
        return {'text': handle.read(32000).decode('utf-8', errors='replace')}

@app.delete('/api/jobs/{id}')
def delete(id: str):
    with guard:
        if job_or_404(id)['state'] not in TERMINAL:
            raise HTTPException(409, 'Cancel the job before deleting it')
        for root in (s.INPUT, s.OUTPUT):
            directory = s.contained(root, id)
            if directory.exists():
                shutil.rmtree(directory)
        query('DELETE FROM jobs WHERE id=?', (id,))
    return {'deleted': True}

STATIC = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get('/')
@app.get('/separator')
@app.get('/applio')
@app.get('/setup')
def page():
    return FileResponse(STATIC / 'index.html')
