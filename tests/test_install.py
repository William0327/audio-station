import json
from types import SimpleNamespace
import pytest
from scripts import install


def fake_runner(**overrides):
    calls = []
    def runner(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ['docker', 'info']:
            return json.dumps({'OSType':'linux','Architecture':'x86_64','SecurityOptions':[]} | overrides.get('info', {}))
        if argv[:3] == ['docker','compose','version']:
            return overrides.get('compose', '2.30.0')
        if argv[:3] == ['docker','context','inspect']:
            return json.dumps([{'Endpoints':{'docker':{'Host':overrides.get('context','unix:///var/run/docker.sock')}}}])
        if argv[0] == 'nvidia-smi':
            return overrides.get('driver','570.124.06')
        if argv[0:2] == ['docker','run']:
            if 'nvidia-smi' in argv and overrides.get('probe_fail'):
                raise install.InstallError('could not select device driver')
            return str(overrides.get('free', 40*1024**3)) if 'df' in argv else 'GPU probe OK'
        raise AssertionError(argv)
    return runner, calls


def test_preflight_validates_without_workload_start(monkeypatch):
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    runner, calls = fake_runner()
    install.preflight({}, runner, 'Linux', 'x86_64', lambda p:SimpleNamespace(free=40*1024**3))
    assert any('--gpus' in call for call in calls)
    assert all('up' not in call and 'create' not in call and 'start' not in call for call in calls)


@pytest.mark.parametrize('overrides,match', [
    ({'compose':'2.20.0'},'Compose'), ({'driver':'550.54.14'},'driver'),
    ({'context':'ssh://elsewhere'},'rootful'), ({'probe_fail':True},'Toolkit'),
    ({'free':1024},'storage'), ({'info':{'SecurityOptions':['name=rootless']}},'rootful'),
])
def test_preflight_actionable_failures(overrides, match, monkeypatch):
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    runner, _ = fake_runner(**overrides)
    with pytest.raises(install.InstallError, match=match):
        install.preflight({},runner,'Linux','x86_64',lambda p:SimpleNamespace(free=40*1024**3))


def test_preflight_rejects_unsupported_and_low_disk():
    with pytest.raises(install.InstallError, match='Linux'):
        install.preflight({}, system='Windows')
    runner, _ = fake_runner()
    with pytest.raises(install.InstallError, match='GiB'):
        install.preflight({},runner,'Linux','x86_64',lambda p:SimpleNamespace(free=1))


@pytest.mark.parametrize('env', [
    {'BIND_ADDRESS':'0.0.0.0'}, {'BIND_ADDRESS':'8.8.8.8'},
    {'STATION_INSTANCE':'../oops'}, {'CONTROLLER_PORT':'22'}, {'APPLIO_PORT':'8080'},
    {'DEPLOYMENT_MODE':'external'},
])
def test_config_rejects_invalid_or_implicit_external_mapping(env):
    with pytest.raises(install.InstallError):
        install.validate_config(env)


def test_configuration_is_idempotent_and_preserves_values(tmp_path):
    path=tmp_path/'.env'
    path.write_text('# Keep this comment\nCONTROLLER_PORT=8181\nSTATION_INSTANCE=studio\nGATEWAY_TOKEN=\n')
    first=install.configure(path,install.read_env(path))
    original=path.read_bytes()
    second=install.configure(path,install.read_env(path))
    assert first == second
    assert len(first['GATEWAY_TOKEN']) == 64
    assert first['CONTROLLER_PORT'] == '8181'
    assert first['WORKLOAD_NETWORK'] == 'studio-workloads'
    assert original == path.read_bytes()
    assert '# Keep this comment' in path.read_text()


def test_volume_creation_is_repeatable_and_never_deletes():
    existing={};calls=[]
    def runner(argv,**kwargs):
        calls.append(argv)
        if argv[:3]==['docker','volume','inspect']:
            if argv[3] not in existing:
                raise install.InstallError('no such volume')
            return json.dumps([existing[argv[3]]])
        if argv[:3]==['docker','volume','create']:
            existing[argv[-1]]={'Labels':{'io.audio-station.managed':'audio-station'}}
        return ''
    install.volumes({},runner)
    count=len([c for c in calls if c[:3]==['docker','volume','create']])
    install.volumes({},runner)
    assert count==9
    assert len([c for c in calls if c[:3]==['docker','volume','create']])==9
    assert all('rm' not in c and 'chown -R' not in c for c in calls)


def test_volume_collision_preserves_unowned_data():
    def runner(argv,**kwargs):
        assert argv[:3]==['docker','volume','inspect']
        return json.dumps([{'Labels':{}}])
    with pytest.raises(install.InstallError,match='ownership'):
        install.volumes({},runner)


def test_external_mode_does_not_force_a_new_driver(monkeypatch):
    monkeypatch.delenv('DOCKER_HOST',raising=False)
    env={'DEPLOYMENT_MODE':'external','SEPARATOR_CONTAINER':'existing-separator',
         'APPLIO_CONTAINER':'existing-applio','HOST_INPUT_DIR':'/srv/audio/input',
         'HOST_OUTPUT_DIR':'/srv/audio/output','HOST_MODELS_DIR':'/srv/audio/models',
         'WORKLOAD_NETWORK':'existing-network','WORKLOAD_NETWORK_EXTERNAL':'true'}
    runner,calls=fake_runner(driver='550.54.14')
    install.preflight(env,runner,'Linux','x86_64',lambda p:SimpleNamespace(free=40*1024**3))
    probe=next(call for call in calls if '--gpus' in call)
    assert 'ubuntu:24.04' in probe
    assert install.GPU_IMAGE not in probe
