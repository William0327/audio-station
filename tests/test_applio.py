import hashlib
import json
import sqlite3
import runpy
import sys
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from controller import app as panel, gateway as engine, settings as s, adapters, voices


@pytest.fixture
def workstation(tmp_path,monkeypatch):
    for name in ('DATA','INPUT','OUTPUT','MODELS'):
        path=tmp_path/name.lower()
        path.mkdir()
        monkeypatch.setattr(s,name,path)
    monkeypatch.setattr(s,'DEPLOYMENT_MODE','managed')
    monkeypatch.setattr(adapters,'MODE','managed')
    (s.MODELS/'local.onnx').write_bytes(b'test separator')
    state={'separator':'ready','applio':'ready'}
    calls=[]
    entered=threading.Event()
    release=threading.Event()
    behavior={'block':False,'fail':False}
    def gateway(method,path,**kwargs):
        calls.append((method,path,kwargs))
        if path=='/applio/voices': return voices.listing()
        if path=='/applio/voices/import': return voices.commit_import(voices.VoiceImport(**kwargs['json']))
        if path in {'/applio/run','/separator/run'}:
            entered.set()
            if behavior['block']: assert release.wait(8)
            if behavior['fail']: raise HTTPException(503,'Gateway disconnected')
            job=kwargs['json']
            destination=s.OUTPUT/job['id']
            (destination/'converted.wav').write_bytes(b'RIFFconverted')
            (destination/'process.log').write_text('Converted test audio')
            return {'exit_code':0}
        if path=='/gpu': return {'available':False}
        parts=path.split('/')
        if parts[1]=='services':
            tool=parts[2]
            if len(parts)>3:
                state[tool]='stopped' if parts[3]=='stop' else 'ready'
                if parts[3]=='stop': release.set()
            return {'state':state[tool],'installed':True}
        raise AssertionError(path)
    monkeypatch.setattr(panel,'gateway',gateway)
    panel.transitions.clear()
    with TestClient(panel.app) as client:
        yield client,state,calls,entered,release,behavior
        release.set()


def import_asset(client,name='voice.pth',content=b'trusted test asset'):
    response=client.post('/api/applio/voices',params={'filename':name,'confirm':True},content=content)
    assert response.status_code==201,response.text
    return response.json()


def conversion(client,model,key='conversion-key-1',**settings):
    return client.post('/api/applio/jobs',params={'filename':'song.wav','model':model,**settings},
                       headers={'Idempotency-Key':key},content=b'RIFFaudio')


def wait(client,id,state):
    for _ in range(150):
        row=client.get('/api/jobs/'+id).json()
        if row['state']==state: return row
        time.sleep(.03)
    pytest.fail(str(row))


def test_voice_imports_are_persistent_unique_and_never_overwrite(workstation):
    client,*_=workstation
    first=import_asset(client)
    second=import_asset(client,content=b'another model')
    index=import_asset(client,'voice.index',b'test index')
    assert first['id']!=second['id']
    assert first['sha256']==hashlib.sha256(b'trusted test asset').hexdigest()
    library=client.get('/api/applio/voices').json()
    assert len(library['models'])==2 and len(library['indexes'])==1
    assert voices.asset_path(first['id'],'.pth').read_bytes()==b'trusted test asset'
    assert voices.asset_path(index['id'],'.index').read_bytes()==b'test index'
    assert not list((s.INPUT/'voice-imports').iterdir())


def test_voice_upload_validation_and_limits(workstation,monkeypatch):
    client,*_=workstation
    assert client.post('/api/applio/voices?filename=v.pth',content=b'model').status_code==409
    assert client.post('/api/applio/voices?filename=v.zip&confirm=true',content=b'zip').status_code==422
    assert client.post('/api/applio/voices?filename=v.pth&confirm=true',content=b'').status_code==422
    monkeypatch.setattr(s,'MAX_VOICE_IMPORT',3)
    assert client.post('/api/applio/voices?filename=v.pth&confirm=true',content=b'large').status_code==413
    assert not s.VOICES.exists()
    monkeypatch.setattr(s,'DEPLOYMENT_MODE','external')
    assert client.post('/api/applio/voices?filename=v.pth&confirm=true',content=b'a').status_code==409


def test_conversion_settings_results_and_idempotency(workstation):
    client,state,calls,*_=workstation
    model=import_asset(client)['id']
    index=import_asset(client,'voice.index')['id']
    response=conversion(client,model,index=index,pitch=5)
    assert response.status_code==201,response.text
    job=response.json()
    completed=wait(client,job['id'],'completed')
    assert completed['tool']=='applio'
    assert json.loads(completed['options'])['pitch']==5
    assert conversion(client,model,index=index,pitch=5).json()['id']==job['id']
    assert conversion(client,model,index=index,pitch=6).status_code==409
    assert conversion(client,model,key='invalid-pitch',pitch=25).status_code==422
    assert conversion(client,'../bad.pth',key='invalid-model').status_code==422
    result=client.get('/api/jobs/'+job['id']+'/results').json()[0]
    assert client.get(result['url']).content==b'RIFFconverted'
    assert '/applio/run' in [call[1] for call in calls]
    assert state['applio']=='ready'


def test_shared_queue_and_tool_scoped_stop(workstation):
    client,state,calls,entered,release,behavior=workstation
    model=import_asset(client)['id']
    behavior['block']=True
    first=conversion(client,model).json()
    assert entered.wait(5)
    separator=client.post('/api/separator/jobs?filename=a.wav&model=local.onnx',
                          headers={'Idempotency-Key':'separator-key'},content=b'audio').json()
    second=conversion(client,model,key='conversion-key-2').json()
    assert client.get('/api/jobs/'+separator['id']).json()['state']=='queued'
    assert client.post('/api/services/applio/stop').status_code==409
    assert client.post('/api/services/applio/stop?confirm=true').status_code==200
    assert wait(client,first['id'],'cancelled')
    assert wait(client,second['id'],'cancelled')
    assert wait(client,separator['id'],'completed')
    assert state['separator']=='ready' and state['applio']=='stopped'


def test_conversion_disconnect_stops_correct_container(workstation):
    client,state,calls,_,_,behavior=workstation
    model=import_asset(client)['id']
    behavior['fail']=True
    job=conversion(client,model).json()
    assert 'disconnected' in wait(client,job['id'],'failed')['error']
    assert state['applio']=='stopped' and state['separator']=='ready'


def test_cancel_running_conversion_preserves_separator_queue(workstation):
    client,state,_,entered,_,behavior=workstation
    model=import_asset(client)['id']
    behavior['block']=True
    job=conversion(client,model).json()
    assert entered.wait(5)
    separator=client.post('/api/separator/jobs?filename=a.wav&model=local.onnx',
                          headers={'Idempotency-Key':'separator-key'},content=b'audio').json()
    assert client.post('/api/jobs/'+job['id']+'/cancel').json()['state']=='cancelled'
    assert wait(client,separator['id'],'completed')
    assert state['applio']=='stopped' and state['separator']=='ready'


def test_voice_checksum_failure_keeps_existing_files(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'INPUT',tmp_path/'input')
    s.VOICES.mkdir()
    existing=s.VOICES/'existing.pth'
    existing.write_bytes(b'keep')
    id='b'*32
    source=s.INPUT/'voice-imports'/id
    source.mkdir(parents=True,exist_ok=True)
    (source/'asset').write_bytes(b'corrupt')
    item=voices.VoiceImport(id=id,filename='voice.pth',size=7,sha256='0'*64)
    with pytest.raises(HTTPException,match='422'):
        voices.commit_import(item)
    assert existing.read_bytes()==b'keep'
    assert not (s.VOICES/'audio-station-imports'/id).exists()


@pytest.mark.parametrize('format',['WAV','FLAC','MP3'])
def test_conversion_wrapper_validates_output_and_passes_fixed_defaults(tmp_path,monkeypatch,format):
    launcher=runpy.run_path(str(Path(__file__).resolve().parents[1]/'deploy/applio/convert_applio.py'))
    monkeypatch.setattr(launcher['os'],'chdir',lambda path:None)
    monkeypatch.setattr(sys,'path',sys.path.copy())
    original=Path.is_file
    monkeypatch.setattr(Path,'is_file',lambda self:True if str(self).replace('\\','/').startswith('/app/rvc/models/') else original(self))
    captured={}
    def infer(**kwargs):
        captured.update(kwargs)
        Path(kwargs['output_path'].replace('.wav','.'+format.lower())).write_bytes(b'converted')
        return ('Converted',kwargs['output_path'])
    monkeypatch.setitem(sys.modules,'core',SimpleNamespace(run_infer_script=infer))
    payload={'input':'/input/source.wav','output':str(tmp_path/('converted.'+format.lower())),
             'model':'/app/logs/voice.pth','index':'','format':format,
             'options':voices.ConversionOptions(pitch=2).model_dump()}
    launcher['convert'](payload)
    assert captured['pitch']==2 and captured['embedder_model']=='contentvec'
    assert captured['split_audio'] is False and captured['f0_autotune'] is False
    Path(payload['output']).unlink()
    monkeypatch.setitem(sys.modules,'core',SimpleNamespace(run_infer_script=lambda **kwargs:None))
    with pytest.raises(RuntimeError,match='no converted audio'):
        launcher['convert'](payload)


def test_gateway_conversion_uses_only_fixed_command_and_validated_paths(tmp_path,monkeypatch):
    monkeypatch.setattr(adapters,'MODE','managed')
    monkeypatch.setattr(s,'TOKEN','test-secret')
    monkeypatch.setattr(s,'INPUT',tmp_path/'input')
    monkeypatch.setattr(s,'OUTPUT',tmp_path/'output')
    s.VOICES.mkdir()
    (s.VOICES/'voice.pth').write_bytes(b'model')
    job={'id':'a'*32,'extension':'.wav','model':'voice.pth','format':'WAV','options':{'pitch':3}}
    source=s.INPUT/job['id']
    source.mkdir(parents=True)
    (source/'source.wav').write_bytes(b'audio')
    captured=[]
    class API:
        def exec_create(self,id,argv,**kwargs):
            captured.append(argv)
            return {'Id':'conversion'}
        def exec_start(self,id,stream): return iter([b'Conversion log'])
        def exec_inspect(self,id): return {'ExitCode':0}
    monkeypatch.setattr(engine,'container',lambda tool:SimpleNamespace(id='owned-applio',status='running',attrs={'Config':{'Image':adapters.TOOLS['applio'].image}}))
    monkeypatch.setattr(engine.docker,'from_env',lambda:SimpleNamespace(api=API()))
    headers={'X-Gateway-Token':s.TOKEN}
    with TestClient(engine.app) as client:
        assert client.post('/applio/run',json=job,headers=headers).json()=={'exit_code':0}
        assert captured[0][:2]==['python3','/station/convert_applio.py']
        payload=json.loads(captured[0][2])
        assert payload['model']=='/app/logs/voice.pth'
        assert payload['input']==f"/input/{job['id']}/source.wav"
        assert payload['options']['pitch']==3
        assert client.post('/applio/run',json=job|{'model':'../foreign.pth'},headers=headers).status_code==422
        assert client.post('/applio/run',json=job|{'options':{'pitch':99}},headers=headers).status_code==422
        monkeypatch.setattr(engine,'container',lambda tool:SimpleNamespace(id='old-applio',status='running',attrs={'Config':{'Image':'audio-station/applio:3.5.1-1'}}))
        assert client.post('/applio/run',json=job,headers=headers).status_code==409
        engine.run_lock.acquire()
        try:
            assert client.post('/applio/run',json=job,headers=headers).status_code==409
        finally: engine.run_lock.release()
        monkeypatch.setattr(adapters,'MODE','external')
        assert client.post('/applio/run',json=job,headers=headers).status_code==409


def test_existing_job_database_migrates_without_losing_history(tmp_path,monkeypatch):
    for name in ('DATA','INPUT','OUTPUT','MODELS'):
        path=tmp_path/name
        path.mkdir()
        monkeypatch.setattr(s,name,path)
    with sqlite3.connect(s.DATA/'jobs.sqlite') as db:
        db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,filename TEXT NOT NULL,extension TEXT NOT NULL,size INTEGER NOT NULL,model TEXT NOT NULL,format TEXT NOT NULL,state TEXT NOT NULL,created TEXT NOT NULL,started TEXT,finished TEXT,error TEXT)')
        db.execute("INSERT INTO jobs VALUES ('legacy','legacy-key','old.wav','.wav',1,'old.onnx','WAV','completed','now',NULL,NULL,NULL)")
    with TestClient(panel.app) as client:
        row=client.get('/api/jobs/legacy').json()
        assert row['tool']=='separator' and row['options']=='{}'
        assert row['filename']=='old.wav' and row['state']=='completed'
