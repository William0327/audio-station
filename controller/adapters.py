"""Fixed tool specifications and ownership-aware Docker lifecycle adapters.

No request can supply an image, mount, device, network, or command.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import docker
from fastapi import HTTPException

OWNER = 'io.audio-station.managed'
INSTANCE = os.getenv('STATION_INSTANCE', 'audio-station')
NETWORK = os.getenv('WORKLOAD_NETWORK', 'audio-station-workloads')
MODE = os.getenv('DEPLOYMENT_MODE', 'managed')


@dataclass(frozen=True)
class Tool:
    id: str
    title: str
    version: str
    image: str
    command: tuple


TOOLS = {
    'separator': Tool('separator', 'Audio Separator', '0.47.0',
                      'audio-station/separator:0.47.0-1', ('python3', '-c', 'import time; time.sleep(10**9)')),
    'applio': Tool('applio', 'Applio', '3.5.1',
                   'audio-station/applio:3.5.1-1', ('python3', '/station/launch_applio.py')),
}


class ToolAdapter(Protocol):
    def inspect(self, client): ...
    def provision(self, client, progress): ...
    def start(self, container): ...
    def stop(self, container): ...


class ContainerLifecycle:
    def start(self, container):
        container.start()

    def stop(self, container):
        container.stop(timeout=10)


class ExternalAdapter(ContainerLifecycle):
    def __init__(self, tool):
        self.tool = tool
        self.name = os.getenv(f'{tool.id.upper()}_CONTAINER', f'ai-{tool.id}')

    def inspect(self, client):
        return client.containers.get(self.name)

    def provision(self, client, progress):
        raise HTTPException(409, 'External mode never installs or modifies workloads. Attach an existing container in configuration.')


class ManagedAdapter(ContainerLifecycle):
    def __init__(self, tool):
        self.tool = tool
        self.name = f'{INSTANCE}-{tool.id}'

    def inspect(self, client):
        container = client.containers.get(self.name)
        labels = container.labels
        if labels.get(OWNER) != INSTANCE or labels.get('io.audio-station.tool') != self.tool.id:
            raise HTTPException(409, 'Container name collision: refusing to adopt an unowned container. Use external mode or another instance name.')
        return container

    def provision(self, client, progress):
        try:
            existing = self.inspect(client)
            if existing.attrs['Config']['Image'] != self.tool.image:
                raise HTTPException(409, 'Installed workload image differs from this release. Follow the upgrade guide; no container was replaced.')
            progress('Already installed; runtime state preserved', 100)
            return
        except docker.errors.NotFound:
            pass
        progress('Building pinned upstream application (first install can take several minutes)', None)
        context = Path(__file__).resolve().parent.parent / 'deploy' / self.tool.id
        # Build only shipped Docker contexts. Neither paths nor build args come from HTTP.
        for item in client.api.build(path=str(context), tag=self.tool.image, rm=True, decode=True, forcerm=True):
            if item.get('error'):
                raise RuntimeError(item['error'][:1000])
            line = item.get('stream') or item.get('status')
            if line:
                progress(str(line).strip()[-500:], None)
        # Recheck after a long build; never replace a concurrently-created container.
        try:
            self.inspect(client)
            return
        except docker.errors.NotFound:
            pass
        prefix = INSTANCE
        def storage(env, default):
            return os.getenv(env) or f'{prefix}-{default}'
        if self.tool.id == 'separator':
            volumes = {
                storage('HOST_INPUT_DIR', 'input'): {'bind': '/input', 'mode': 'ro'},
                storage('HOST_OUTPUT_DIR', 'output'): {'bind': '/output', 'mode': 'rw'},
                storage('HOST_MODELS_DIR', 'models'): {'bind': '/models', 'mode': 'ro'},
            }
            ports = None
            environment = {'HF_HOME': '/tmp/hf', 'TORCH_HOME': '/tmp/torch'}
        else:
            volumes = {
                f'{prefix}-applio-models': {'bind': '/app/rvc/models', 'mode': 'rw'},
                f'{prefix}-applio-assets': {'bind': '/app/assets', 'mode': 'rw'},
                f'{prefix}-applio-logs': {'bind': '/app/logs', 'mode': 'rw'},
                f'{prefix}-applio-cache': {'bind': '/cache', 'mode': 'rw'},
            }
            ports = {'6969/tcp': (os.getenv('BIND_ADDRESS', '127.0.0.1'), int(os.getenv('APPLIO_PORT', '6969')))}
            environment = {'HF_HOME': '/cache/huggingface', 'TORCH_HOME': '/cache/torch', 'GRADIO_ANALYTICS_ENABLED': 'False'}
        container = client.containers.create(
            self.tool.image, name=self.name, command=list(self.tool.command), entrypoint=[],
            labels={OWNER: INSTANCE, 'io.audio-station.tool': self.tool.id, 'io.audio-station.version': self.tool.version},
            volumes=volumes, ports=ports, network=NETWORK, environment=environment,
            device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
            restart_policy={'Name': 'no'}, init=True, security_opt=['no-new-privileges:true'], cap_drop=['ALL'],
        )
        # Docker create leaves the workload stopped. Installation never calls start.
        progress('Installed and stopped. Start explicitly when ready.', 100)


def adapter(service):
    if service not in TOOLS:
        raise HTTPException(404, 'Unknown service')
    if MODE not in {'managed', 'external'}:
        raise HTTPException(503, 'DEPLOYMENT_MODE must be managed or external')
    return ManagedAdapter(TOOLS[service]) if MODE == 'managed' else ExternalAdapter(TOOLS[service])
