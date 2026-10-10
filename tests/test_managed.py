from types import SimpleNamespace
import time
import docker
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from controller import adapters, gateway, operations


def client_with_containers(existing=None, collision=False):
    calls=[]
    class Containers:
        current=existing
        def get(self,name):
            if self.current is None:
                raise docker.errors.NotFound('missing')
            return self.current
        def create(self,image,**kwargs):
            calls.append((image,kwargs))
            self.current=SimpleNamespace(labels=kwargs['labels'],attrs={'Config':{'Image':image},'State':{'Running':False}},status='created')
            return self.current
    containers=Containers()
    client=SimpleNamespace(containers=containers,api=SimpleNamespace(build=lambda **kwargs:iter([{'stream':'building'},{'stream':'done'}])))
    return client,calls


@pytest.mark.parametrize('name', ['separator','applio'])
def test_managed_install_is_stopped_scoped_and_idempotent(name,monkeypatch):
    monkeypatch.setattr(adapters,'MODE','managed')
    client,calls=client_with_containers()
    adapter=adapters.adapter(name)
    progress=[]
    adapter.provision(client,lambda message,percent:progress.append((message,percent)))
    adapter.provision(client,lambda *args:None)
    assert len(calls)==1
    image,config=calls[0]
    assert config['labels'][adapters.OWNER]==adapters.INSTANCE
    assert config['restart_policy']=={'Name':'no'}
    assert config['entrypoint']==[]
    assert config['device_requests'][0]['Capabilities']==[['gpu']]
    assert config['name']==adapters.INSTANCE+'-'+name
    assert client.containers.current.status=='created'
    assert progress[-1][1]==100


def test_managed_name_collision_and_version_change_are_not_adopted(monkeypatch):
    monkeypatch.setattr(adapters,'MODE','managed')
    existing=SimpleNamespace(labels={},attrs={'Config':{'Image':'foreign'}})
    client,calls=client_with_containers(existing)
    with pytest.raises(HTTPException,match='409'):
        adapters.adapter('separator').provision(client,lambda *args:None)
    existing.labels={adapters.OWNER:adapters.INSTANCE,'io.audio-station.tool':'separator'}
    with pytest.raises(HTTPException,match='409'):
        adapters.adapter('separator').provision(client,lambda *args:None)
    assert calls==[]


def test_external_adapter_never_provisions(monkeypatch):
    monkeypatch.setattr(adapters,'MODE','external')
    with pytest.raises(HTTPException):
        adapters.adapter('separator').provision(None,None)


def test_first_run_detection_and_pending_install_blocks_start(monkeypatch):
    monkeypatch.setattr(adapters,'MODE','managed')
    client,_=client_with_containers()
    monkeypatch.setattr(gateway.docker,'from_env',lambda **kwargs:client)
    monkeypatch.setattr(gateway.s,'TOKEN','test-private-token')
    headers={'X-Gateway-Token':gateway.s.TOKEN}
    with TestClient(gateway.app) as web:
        state=web.get('/setup',headers=headers).json()
        assert all(not info['installed'] and info['state']=='stopped' for info in state['tools'].values())
        operations.stop()
        operations.sql("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?)",('pending','tool','separator','separator','queued','wait',None,'now'))
        assert web.post('/services/separator/start',headers=headers).status_code==409
        assert web.post('/install/arbitrary',headers=headers).status_code==404


def test_install_operation_recovery_and_durable_queue():
    operations.start()
    operations.stop()
    operations.sql('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?)',('interrupted','tool','separator','separator','running','build',None,'now'))
    operations.start()
    try:
        job=operations.sql('SELECT * FROM operations WHERE id=?',('interrupted',))[0]
        assert job['state']=='failed'
        assert 'restarted' in job['message']
    finally:
        operations.stop()


def test_install_submission_is_durable_and_deduplicated(monkeypatch):
    monkeypatch.setattr(adapters,'MODE','managed')
    client,_=client_with_containers()
    monkeypatch.setattr(operations.docker,'from_env',lambda **kwargs:client)
    operations.start()
    operations.stop()
    first=operations.submit('tool','separator')
    second=operations.submit('tool','separator')
    assert first['id']==second['id']
    assert operations.sql('SELECT * FROM operations')[0]['state']=='queued'
    with pytest.raises(HTTPException):
        operations.submit('model','not-in-catalogue')
    with pytest.raises(HTTPException):
        operations.submit('model','uvr-karaoke')


def test_external_model_mutations_are_disabled(monkeypatch):
    monkeypatch.setattr(adapters,'MODE','external')
    with pytest.raises(HTTPException):
        operations.submit('model','uvr-karaoke')


def test_gateway_install_api_completes_without_starting_workload(monkeypatch):
    monkeypatch.setattr(adapters,'MODE','managed')
    client,calls=client_with_containers()
    monkeypatch.setattr(gateway.docker,'from_env',lambda **kwargs:client)
    monkeypatch.setattr(gateway.s,'TOKEN','private-test-value')
    headers={'X-Gateway-Token':gateway.s.TOKEN}
    with TestClient(gateway.app) as web:
        response=web.post('/install/separator',headers=headers)
        assert response.status_code==200
        id=response.json()['id']
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            state=web.get('/setup',headers=headers).json()
            op=next(o for o in state['operations'] if o['id']==id)
            if op['state']=='completed':
                break
            time.sleep(.05)
        assert op['state']=='completed',op
        state=web.get('/setup',headers=headers).json()
        assert state['tools']['separator']['installed'] is True
        assert state['tools']['separator']['state']=='stopped'
        assert len(calls)==1
        assert web.delete('/models/uvr-karaoke',headers=headers).status_code==409
