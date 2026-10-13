from pathlib import Path
import subprocess
import yaml
from scripts import check_release

ROOT=Path(__file__).resolve().parent.parent


def test_workload_build_files_are_present_and_not_gitignored():
    files=[f'deploy/{tool}/{name}' for tool in ('separator','applio')
           for name in ('Dockerfile',f'launch_{tool}.py')]
    for name in files:
        assert (ROOT/name).is_file(), f'Missing shipped build file: {name}'
    if (ROOT/'.git').exists():
        result=subprocess.run(['git','check-ignore','--no-index',*files],cwd=ROOT,
                              capture_output=True,text=True)
        assert result.returncode==1, result.stdout or result.stderr


def test_compose_profiles_and_privilege_boundary():
    config=yaml.safe_load((ROOT/'compose.yaml').read_text())
    services=config['services']
    assert set(services)=={'controller','gateway','separator','applio'}
    assert services['separator']['profiles']==['separator']
    assert services['applio']['profiles']==['applio']
    assert services['separator']['restart']=='no'
    assert services['applio']['restart']=='no'
    assert services['separator']['shm_size']=='4g'
    assert services['applio']['shm_size']=='4g'
    assert 'ports' not in services['gateway']
    assert all('docker.sock' not in volume for volume in services['controller']['volumes'])
    assert 'deploy' not in services['controller']
    assert set(config['volumes']) >= {'station-models','station-data','station-state','applio-models','applio-cache'}


def test_controller_has_publishable_network_without_exposing_gateway():
    config=yaml.safe_load((ROOT/'compose.yaml').read_text())
    services=config['services']
    networks=config['networks']
    controller_networks=set(services['controller']['networks'])
    gateway_networks=set(services['gateway']['networks'])
    assert networks['control']['internal'] is True
    assert 'control' in controller_networks & gateway_networks
    web_networks={name for name in controller_networks if not networks[name].get('internal',False)}
    assert web_networks, 'Internal-only networks do not provide host port publishing'
    assert web_networks.isdisjoint(gateway_networks)
    assert 'ports' not in services['gateway']


def test_release_source_hygiene():
    assert check_release.check(check_release.source_files())==[]


def test_declared_upstream_images_match_adapters():
    from controller.adapters import TOOLS
    config=yaml.safe_load((ROOT/'compose.yaml').read_text())
    for id,tool in TOOLS.items():
        service=config['services'][id]
        assert service['image']==tool.image
        assert tuple(service['command'])==tool.command
        assert service['labels']['io.audio-station.version']==tool.version
