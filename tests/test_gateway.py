from types import SimpleNamespace

from fastapi.testclient import TestClient
from controller import gateway as engine
from controller import settings as s


def test_fixed_execution_argv_and_log_capture(tmp_path, monkeypatch):
    job_id = 'a' * 32
    for name in ('INPUT', 'OUTPUT', 'MODELS'):
        path = tmp_path / name
        path.mkdir()
        monkeypatch.setattr(s, name, path)
    (s.MODELS / 'local.onnx').write_bytes(b'model')
    (s.INPUT / job_id).mkdir()
    (s.INPUT / job_id / 'source.wav').write_bytes(b'audio')
    monkeypatch.setattr(s, 'TOKEN', 'test-secret')
    monkeypatch.setenv('SEPARATOR_BINARY', '/venv/bin/audio-separator')
    captured = {}
    class EngineAPI:
        def exec_create(self, id, argv, **kwargs):
            captured.update(id=id, argv=argv)
            return {'Id': 'exec123'}
        def exec_start(self, id, stream):
            assert id == 'exec123' and stream
            return iter([b'Loading local model\n', b'Completed\n'])
        def exec_inspect(self, id):
            return {'ExitCode': 0}
    container = SimpleNamespace(id='approved-separator', status='running')
    def get(name):
        assert name == engine.adapters.adapter('separator').name
        return container
    monkeypatch.setattr(engine.docker, 'from_env', lambda: SimpleNamespace(containers=SimpleNamespace(get=get), api=EngineAPI()))
    with TestClient(engine.app) as client:
        response = client.post('/separator/run', json={'id':job_id, 'extension':'.wav', 'model':'local.onnx', 'format':'WAV'}, headers={'X-Gateway-Token':s.TOKEN})
        assert response.json() == {'exit_code': 0}
    assert captured['argv'] == ['/venv/bin/audio-separator', f'/input/{job_id}/source.wav', '--model_filename', 'local.onnx', '--model_file_dir', '/models', '--output_dir', f'/output/{job_id}', '--output_format', 'WAV']
    assert (s.OUTPUT / job_id / 'process.log').read_text() == 'Loading local model\nCompleted\n'


def test_scoped_lifecycle_and_readiness(monkeypatch):
    monkeypatch.setattr(s, 'TOKEN', 'test-secret')
    calls = []
    class Container:
        attrs = {'State': {'Running': True}}
        def start(self): calls.append('start')
        def stop(self, timeout): calls.append(('stop', timeout))
    monkeypatch.setattr(engine, 'container', lambda service: Container())
    monkeypatch.setattr(engine.httpx, 'get', lambda *args, **kwargs: SimpleNamespace(status_code=200))
    headers = {'X-Gateway-Token': s.TOKEN}
    with TestClient(engine.app) as client:
        assert client.post('/services/separator/start', headers=headers).json()['state'] == 'starting'
        assert client.post('/services/separator/stop', headers=headers).status_code == 200
        assert calls == ['start', ('stop', 10)]
        assert client.get('/services/applio', headers=headers).json()['state'] == 'ready'
        monkeypatch.setattr(engine.httpx, 'get', lambda *args, **kwargs: SimpleNamespace(status_code=503))
        assert client.get('/services/applio', headers=headers).json()['state'] == 'starting'
        assert client.post('/services/separator/remove', headers=headers).status_code == 404
