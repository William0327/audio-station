"""The only component with socket access. No arbitrary Docker API forwarding."""
import hmac
import json
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
import docker
import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from controller import settings as s
from controller import adapters, operations, model_manager
from controller.catalog import CATALOG

@asynccontextmanager
async def lifespan(app):
    operations.start()
    yield
    operations.stop()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
names = {name: adapters.adapter(name).name for name in adapters.TOOLS}
run_lock = threading.Lock()

@app.middleware('http')
async def authenticate(request: Request, call_next):
    if request.url.path != '/health' and (not s.TOKEN or not hmac.compare_digest(request.headers.get('x-gateway-token', ''), s.TOKEN)):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Unauthorized'}, status_code=401)
    return await call_next(request)

def container(service):
    if service not in names:
        raise HTTPException(404, 'Unknown service')
    try:
        return adapters.adapter(service).inspect(docker.from_env())
    except docker.errors.NotFound:
        message = 'Tool is not installed; use Setup & models' if adapters.MODE == 'managed' else 'External container not found; check its configured mapping'
        raise HTTPException(404, message)
    except docker.errors.DockerException:
        raise HTTPException(503, 'Docker Engine unavailable')

@app.get('/health')
def health():
    return {'ok': True}


def stop_identity(c):
    state = c.attrs['State']
    return {'container': c.id, 'started': state.get('StartedAt'), 'finished': state.get('FinishedAt')}


def remember_stop(service, c):
    directory = s.STATE / 'lifecycle'
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'{service}.json'
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(stop_identity(c)), encoding='utf-8')
    os.replace(temporary, destination)


def intentionally_stopped(service, c):
    try:
        recorded = json.loads((s.STATE / 'lifecycle' / f'{service}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return recorded == stop_identity(c)

@app.get('/services/{service}')
def status(service: str):
    if service not in adapters.TOOLS:
        raise HTTPException(404, 'Unknown service')
    metadata = {'mode': adapters.MODE, 'version': adapters.TOOLS[service].version}
    try:
        c = container(service)
    except HTTPException as exc:
        if exc.status_code == 404:
            return metadata | {'installed': False, 'state': 'stopped', 'error': None}
        raise
    state = c.attrs['State']
    result = metadata | {'installed': True, 'state': 'stopped', 'error': state.get('Error') or None}
    if state.get('Restarting'):
        result['state'] = 'starting'
    elif state.get('Running'):
        health = state.get('Health', {}).get('Status')
        result['state'] = 'error' if health == 'unhealthy' else 'starting' if health == 'starting' else 'ready'
        if service == 'applio' and result['state'] == 'ready':
            try:
                default_url = f'http://{adapters.adapter(service).name}:6969'
                r = httpx.get(os.getenv('APPLIO_HEALTH_URL') or default_url, timeout=2)
                if r.status_code >= 400:
                    result['state'] = 'starting'
            except httpx.HTTPError:
                result['state'] = 'starting'
    elif state.get('Dead') or state.get('OOMKilled') or state.get('Error'):
        result.update(state='error', error=result['error'] or ('Container was killed by the memory limit' if state.get('OOMKilled') else 'Container is dead'))
    elif state.get('ExitCode', 0) != 0 and not intentionally_stopped(service, c):
        result.update(state='error', error=result['error'] or f"Container exited with code {state.get('ExitCode')}")
    return result

@app.post('/services/{service}/{action}')
def lifecycle(service: str, action: str):
    if action not in {'start', 'stop'}:
        raise HTTPException(404, 'Unknown action')
    with operations.lock:
        if action == 'start' and operations.active(service):
            raise HTTPException(409, 'Wait for the installation operation to finish before starting')
        c = container(service)
        if action == 'start' and service == 'applio' and adapters.MODE == 'managed':
            if not next(x for x in model_manager.listing() if x['id'] == 'applio-essentials')['installed']:
                raise HTTPException(409, 'Install Applio inference essentials from Models before starting')
        try:
            tool_adapter = adapters.adapter(service)
            was_running = c.attrs['State'].get('Running', False)
            tool_adapter.start(c) if action == 'start' else tool_adapter.stop(c)
            if action == 'stop' and was_running:
                c.reload()
                if not c.attrs['State'].get('Running'):
                    remember_stop(service, c)
            return {'state': 'starting' if action == 'start' else 'stopped'}
        except docker.errors.DockerException:
            raise HTTPException(502, 'Docker operation failed; inspect container logs on host')

@app.get('/setup')
def setup():
    tools = {}
    for name, tool in adapters.TOOLS.items():
        try:
            tools[name] = status(name)
        except HTTPException as exc:
            tools[name] = {'installed': False, 'state': 'error', 'error': exc.detail}
        tools[name]['title'] = tool.title
        tools[name]['version'] = tool.version
    return {'mode': adapters.MODE, 'tools': tools, 'models': model_manager.listing(),
            'operations': operations.sql('SELECT * FROM operations ORDER BY created DESC LIMIT 30')}

@app.post('/install/{service}')
def install_tool(service: str):
    return operations.submit('tool', service)

@app.post('/models/{id}/install')
def install_model(id: str):
    return operations.submit('model', id)

@app.delete('/models/{id}')
def delete_model(id: str, confirm: bool = False):
    if not confirm:
        raise HTTPException(409, 'Explicit confirmation is required to delete catalogue model files')
    return operations.submit('remove-model', id)

class Run(BaseModel):
    id: str = Field(pattern=r'^[0-9a-f]{32}$')
    extension: str
    model: str
    format: str

@app.post('/separator/run')
def run(job: Run):
    if job.extension not in s.EXTENSIONS or job.model not in s.installed_models() or job.format not in {'WAV', 'MP3', 'FLAC'}:
        raise HTTPException(422, 'Invalid job configuration')
    if not run_lock.acquire(blocking=False):
        raise HTTPException(409, 'Separator already busy')
    try:
        c = container('separator')
        if c.status != 'running':
            raise HTTPException(409, 'Start Audio Separator before processing')
        source = s.contained(s.INPUT, job.id, 'source' + job.extension)
        if not source.is_file():
            raise HTTPException(404, 'Input missing')
        destination = s.contained(s.OUTPUT, job.id)
        destination.mkdir(parents=True, exist_ok=True)
        # These three paths refer to mounts INSIDE the existing separator container.
        binary = 'station-separate' if adapters.MODE == 'managed' else os.getenv('SEPARATOR_BINARY', 'audio-separator')
        argv = [binary,
                f"{os.getenv('SEPARATOR_INPUT_DIR', '/input')}/{job.id}/source{job.extension}",
                '--model_filename', job.model, '--model_file_dir', os.getenv('SEPARATOR_MODELS_DIR', '/models'),
                '--output_dir', f"{os.getenv('SEPARATOR_OUTPUT_DIR', '/output')}/{job.id}",
                '--output_format', job.format]
        client = docker.from_env().api
        execution = client.exec_create(c.id, argv, stdout=True, stderr=True)
        with (destination / 'process.log').open('wb') as log:
            for chunk in client.exec_start(execution['Id'], stream=True):
                if log.tell() + len(chunk) > 2 * 1024 * 1024:
                    log.seek(0)
                    log.truncate()
                log.write(chunk)
                log.flush()
        return {'exit_code': client.exec_inspect(execution['Id'])['ExitCode']}
    except docker.errors.DockerException:
        raise HTTPException(502, 'Separator execution interrupted or Docker unavailable')
    finally:
        run_lock.release()

@app.get('/gpu')
def gpu():
    c = container('separator')
    if c.status != 'running':
        return {'available': False, 'reason': 'GPU metrics available when separator is running'}
    try:
        result = c.exec_run(['nvidia-smi', '--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu', '--format=csv,noheader,nounits'])
        rows = []
        if result.exit_code != 0:
            raise ValueError()
        for line in result.output.decode().strip().splitlines():
            name, usage, used, total, temperature = [x.strip() for x in line.split(',')]
            rows.append(dict(name=name, utilization=int(usage), used_mb=int(used), total_mb=int(total), temperature=int(temperature)))
        return {'available': True, 'gpus': rows}
    except (ValueError, docker.errors.DockerException):
        return {'available': False, 'reason': 'NVIDIA metrics unavailable'}
