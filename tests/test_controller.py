import io
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from controller import app as panel
from controller import settings as s
from controller import gateway as engine


@pytest.fixture
def environment(tmp_path, monkeypatch):
    for name in ('DATA', 'INPUT', 'OUTPUT', 'MODELS'):
        path = tmp_path / name.lower()
        path.mkdir()
        monkeypatch.setattr(s, name, path)
    (s.MODELS / 'installed.onnx').write_bytes(b'model')
    states = {'separator': 'ready', 'applio': 'stopped'}
    entered = threading.Event()
    release = threading.Event()
    calls = []
    behavior = {'block': False, 'fail': False}

    def gateway(method, path, **kwargs):
        calls.append((method, path))
        if path == '/separator/run':
            job = kwargs['json']
            entered.set()
            if behavior['block']:
                assert release.wait(10), 'Test did not release worker'
            if states['separator'] != 'ready':
                raise HTTPException(502, 'Container stopped')
            output = s.OUTPUT / job['id']
            output.mkdir(exist_ok=True)
            (output / 'process.log').write_text('test execution\n')
            if behavior['fail']:
                return {'exit_code': 1}
            (output / 'Vocals.wav').write_bytes(b'RIFF' + b'\0' * 64)
            (output / 'Instrumental.wav').write_bytes(b'RIFF' + b'\1' * 64)
            return {'exit_code': 0}
        if path == '/gpu':
            return {'available': False, 'reason': 'Test environment'}
        _, _, service, *actions = path.split('/')
        if service not in states:
            raise HTTPException(404, 'Unknown service')
        if actions:
            states[service] = 'ready' if actions[0] == 'start' else 'stopped'
            if actions[0] == 'stop':
                release.set()
        return {'state': states[service]}

    monkeypatch.setattr(panel, 'gateway', gateway)
    panel.transitions.clear()
    with TestClient(panel.app) as client:
        yield client, states, entered, release, calls, behavior
        release.set()


def submit(client, key='submission-0001', **overrides):
    params = {'filename': 'song.wav', 'model': 'installed.onnx', 'format': 'WAV'} | overrides
    return client.post('/api/separator/jobs', params=params, content=b'RIFFaudio', headers={'Idempotency-Key': key})


def wait_job(client, id, state):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        row = client.get('/api/jobs/' + id).json()
        if row['state'] == state:
            return row
        time.sleep(.03)
    pytest.fail(f'Expected {state}, got {row}')


def test_roformer_model_api_uses_friendly_label_and_hides_configuration(environment):
    from controller.catalog import CATALOG
    client, *_ = environment
    entry=CATALOG['bs-roformer-viperx-1297']
    for spec in entry['files']:
        (s.MODELS/spec['path']).write_bytes(b'test asset')
    response=client.get('/api/separator/models').json()
    filename=entry['model_filename']
    assert filename in response['models']
    assert response['labels'][filename]=='BS-RoFormer Viperx 1297'
    assert not any(name.endswith('.yaml') for name in response['models'])


def test_complete_workflow_and_safe_downloads(environment):
    client, *_ = environment
    assert client.get('/').status_code == 200
    assert client.get('/separator').status_code == 200
    assert client.get('/api/separator/models').json()['models'] == ['installed.onnx']
    job = submit(client).json()
    wait_job(client, job['id'], 'completed')
    files = client.get(f"/api/jobs/{job['id']}/results").json()
    assert len(files) == 2
    assert client.get(files[0]['url']).content.startswith(b'RIFF')
    assert client.get(files[0]['url'], headers={'Range': 'bytes=0-3'}).status_code == 206
    archive = client.get(f"/api/jobs/{job['id']}/zip")
    assert set(zipfile.ZipFile(io.BytesIO(archive.content)).namelist()) == {'Instrumental.wav', 'Vocals.wav'}
    assert client.get(f"/api/jobs/{job['id']}/files/process.log").status_code == 404
    assert 'test execution' in client.get(f"/api/jobs/{job['id']}/log").json()['text']
    assert client.delete('/api/jobs/' + job['id']).status_code == 200
    assert not (s.INPUT / job['id']).exists()
    assert not (s.OUTPUT / job['id']).exists()
    assert client.get('/api/jobs/' + job['id']).status_code == 404


def test_idempotency_and_filename_sanitization(environment):
    client, *_ = environment
    first = submit(client, filename='../../somewhere/song.wav').json()
    second = submit(client, filename='../../somewhere/song.wav').json()
    assert first['id'] == second['id']
    assert first['filename'] == 'song.wav'
    assert len(client.get('/api/jobs').json()) == 1
    assert submit(client, format='FLAC').status_code == 409
    assert client.post('/api/separator/jobs', params={'filename': 'a.wav', 'model': 'installed.onnx'}, content=b'a').status_code == 422


@pytest.mark.parametrize('params', [{'filename': 'file.exe'}, {'model': '../secret.onnx'}, {'format': 'SHELL'}])
def test_reject_invalid_input(environment, params):
    client, *_ = environment
    assert submit(client, **params).status_code == 422
    assert client.get('/api/jobs').json() == []


def test_upload_limit_and_empty_cleanup(environment, monkeypatch):
    client, *_ = environment
    monkeypatch.setattr(s, 'MAX_UPLOAD', 2)
    assert submit(client).status_code == 413
    assert list(s.INPUT.iterdir()) == []
    response = client.post('/api/separator/jobs', params={'filename': 'empty.wav', 'model': 'installed.onnx'}, content=b'', headers={'Idempotency-Key': 'empty-00001'})
    assert response.status_code == 422
    assert list(s.INPUT.iterdir()) == []


def test_queue_cancel_and_busy_stop_confirmation(environment):
    client, states, entered, release, calls, behavior = environment
    behavior['block'] = True
    first = submit(client).json()
    assert entered.wait(5)
    second = submit(client, key='submission-0002').json()
    assert second['state'] == 'queued'
    assert client.get('/api/services').json()['separator']['state'] == 'busy'
    assert client.delete('/api/jobs/' + first['id']).status_code == 409
    assert client.post('/api/services/separator/stop').status_code == 409
    assert states['separator'] == 'ready'
    assert client.post('/api/services/separator/stop?confirm=true').status_code == 200
    wait_job(client, first['id'], 'cancelled')
    wait_job(client, second['id'], 'cancelled')
    assert states['separator'] == 'stopped'
    assert len([c for c in calls if c[1] == '/separator/run']) == 1


def test_cancel_running_terminates_container(environment):
    client, states, entered, _, _, behavior = environment
    behavior['block'] = True
    job = submit(client).json()
    assert entered.wait(5)
    assert client.post(f"/api/jobs/{job['id']}/cancel").json()['state'] == 'cancelled'
    assert states['separator'] == 'stopped'


def test_cancel_queued_does_not_stop_running(environment):
    client, states, entered, release, _, behavior = environment
    behavior['block'] = True
    first = submit(client).json()
    assert entered.wait(5)
    second = submit(client, key='submission-0002').json()
    assert client.post(f"/api/jobs/{second['id']}/cancel").json()['state'] == 'cancelled'
    assert states['separator'] == 'ready'
    release.set()
    wait_job(client, first['id'], 'completed')


def test_sequential_jobs_and_process_failure(environment):
    client, _, entered, release, _, behavior = environment
    behavior['block'] = True
    first = submit(client).json()
    assert entered.wait(5)
    second = submit(client, key='submission-0002').json()
    assert second['state'] == 'queued'
    release.set()
    wait_job(client, first['id'], 'completed')
    wait_job(client, second['id'], 'completed')
    behavior['fail'] = True
    third = submit(client, key='submission-0003').json()
    assert 'code 1' in wait_job(client, third['id'], 'failed')['error']


def test_unknown_service_origin_and_gpu(environment):
    client, *_ = environment
    assert client.post('/api/services/arbitrary/start').status_code == 404
    assert client.post('/api/services/separator/start', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/api/services/separator/start', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert client.get('/api/system/gpu').json()['available'] is False
    assert client.get('/').headers['x-content-type-options'] == 'nosniff'


def test_gateway_unavailable_and_stopped_job(environment, monkeypatch):
    client, states, *_ = environment
    states['separator'] = 'stopped'
    job = submit(client).json()
    assert 'must be ready' in wait_job(client, job['id'], 'failed')['error']
    def offline(*args, **kwargs):
        raise HTTPException(503, 'Gateway offline')
    monkeypatch.setattr(panel, 'gateway', offline)
    assert client.get('/api/services').json()['separator']['state'] == 'error'
    assert client.get('/api/system/gpu').json()['available'] is False
    assert client.get('/').status_code == 200


def test_restart_recovery_stops_orphan_before_new_job(environment):
    client, states, *_ = environment
    # Stop the test worker, emulate abrupt termination metadata, then invoke recovery.
    panel.shutdown.set()
    time.sleep(1.1)
    job = submit(client).json()
    panel.query("UPDATE jobs SET state='running' WHERE id=?", (job['id'],))
    panel.shutdown.clear()
    thread = threading.Thread(target=panel.worker, daemon=True)
    thread.start()
    try:
        assert 'restarted' in wait_job(client, job['id'], 'failed')['error']
        assert states['separator'] == 'stopped'
    finally:
        panel.shutdown.set()
        thread.join(3)


def test_gateway_token_and_allowlist(monkeypatch):
    monkeypatch.setattr(s, 'TOKEN', 'gateway-test-secret')
    with TestClient(engine.app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/services/separator').status_code == 401
        assert client.get('/services/other', headers={'X-Gateway-Token': s.TOKEN}).status_code == 404
        assert client.post('/separator/run', json={'id': '../bad', 'extension': '.wav', 'model': 'anything', 'format': 'WAV'}, headers={'X-Gateway-Token': s.TOKEN}).status_code == 422


def test_execution_disconnect_stops_before_dispatch(environment, monkeypatch):
    client, states, _, _, calls, _ = environment
    original = panel.gateway
    def disconnected(method, path, **kwargs):
        if path == '/separator/run':
            raise HTTPException(503, 'Connection lost during inference')
        return original(method, path, **kwargs)
    monkeypatch.setattr(panel, 'gateway', disconnected)
    job = submit(client).json()
    assert 'Connection lost' in wait_job(client, job['id'], 'failed')['error']
    assert states['separator'] == 'stopped'
    assert ('POST', '/services/separator/stop') in calls


def test_missing_gateway_configuration_fails_immediately(monkeypatch):
    monkeypatch.setattr(s, 'TOKEN', '')
    with pytest.raises(HTTPException) as error:
        panel.gateway('GET', '/services/separator')
    assert error.value.status_code == 503
    assert 'not configured' in error.value.detail
