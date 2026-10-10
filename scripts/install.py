"""Idempotent Linux installer. Standard library only; never sources .env as shell."""
import argparse
import ipaddress
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GPU_IMAGE = 'nvidia/cuda:12.8.1-base-ubuntu24.04'
MIN_FREE = 30 * 1024**3


class InstallError(Exception):
    pass


def run(argv, *, capture=True, timeout=120):
    try:
        process = subprocess.run(argv, cwd=ROOT, text=True, capture_output=capture, timeout=timeout)
    except FileNotFoundError:
        raise InstallError(f'{argv[0]} is missing. Install Docker Engine/Compose and NVIDIA drivers/toolkit, then retry.')
    except subprocess.TimeoutExpired:
        raise InstallError(f'{argv[0]} timed out. Check daemon connectivity and registry access, then retry.')
    if process.returncode:
        detail = (process.stderr or process.stdout or '')[-1200:] if capture else ''
        raise InstallError(f"{' '.join(argv[:3])} failed: {detail}")
    return process.stdout or ''


def read_env(path):
    result = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise InstallError('Malformed .env. Use KEY=value lines; no shell commands or export statements.')
        result[key] = value.strip().strip('"\'')
    return result


def validate_config(env):
    mode = env.get('DEPLOYMENT_MODE', 'managed')
    if mode not in {'managed', 'external'}:
        raise InstallError('DEPLOYMENT_MODE must be managed or external.')
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}', env.get('STATION_INSTANCE', 'audio-station')):
        raise InstallError('STATION_INSTANCE must be 2–41 lowercase letters/digits/hyphens, starting with a letter.')
    try:
        ip = ipaddress.ip_address(env.get('BIND_ADDRESS', '127.0.0.1'))
    except ValueError:
        raise InstallError('BIND_ADDRESS must be a specific local/private IPv4 address.')
    tailscale = ip.version == 4 and ip in ipaddress.ip_network('100.64.0.0/10')
    if ip.version != 4 or ip.is_unspecified or not (ip.is_private or ip.is_loopback or tailscale):
        raise InstallError('Refusing public/all-interface binding. Use a specific private or loopback IPv4 address.')
    for key, default in [('CONTROLLER_PORT', '8080'), ('APPLIO_PORT', '6969')]:
        value = env.get(key, default)
        if not value.isdigit() or not 1024 <= int(value) <= 65535:
            raise InstallError(f'{key} must be a port between 1024 and 65535.')
    if env.get('CONTROLLER_PORT', '8080') == env.get('APPLIO_PORT', '6969'):
        raise InstallError('Controller and Applio ports must differ.')
    if mode == 'external':
        required = ['SEPARATOR_CONTAINER', 'APPLIO_CONTAINER', 'HOST_INPUT_DIR', 'HOST_OUTPUT_DIR', 'HOST_MODELS_DIR', 'WORKLOAD_NETWORK']
        missing = [key for key in required if not env.get(key)]
        if missing:
            raise InstallError('External mode needs explicit mappings: ' + ', '.join(missing) + '. See docs/migration.md.')
        if env.get('WORKLOAD_NETWORK_EXTERNAL') != 'true':
            raise InstallError('External mode requires WORKLOAD_NETWORK_EXTERNAL=true to preserve the existing network.')


def preflight(env, runner=run, system=None, machine=None, disk=shutil.disk_usage):
    if (system or platform.system()) != 'Linux' or (machine or platform.machine()) != 'x86_64':
        raise InstallError('v1 supports x86_64 Linux with an NVIDIA GPU. Run this installer on the Linux Docker host.')
    if sys.version_info < (3, 10):
        raise InstallError('Python 3.10+ is required (Ubuntu 22.04/24.04 provides it).')
    validate_config(env)
    info = json.loads(runner(['docker', 'info', '--format', '{{json .}}']))
    version = runner(['docker', 'compose', 'version', '--short']).strip().lstrip('v')
    numbers = re.match(r'(\d+)\.(\d+)', version)
    if not numbers or tuple(map(int, numbers.groups())) < (2, 24):
        raise InstallError('Docker Compose plugin 2.24+ is required. Update the plugin, not legacy docker-compose.')
    if info.get('OSType') != 'linux' or info.get('Architecture') not in {'x86_64', 'amd64'}:
        raise InstallError('Docker daemon must be a local Linux x86_64 daemon.')
    context = json.loads(runner(['docker', 'context', 'inspect']))
    endpoint = context[0]['Endpoints']['docker']['Host']
    if endpoint != 'unix:///var/run/docker.sock' or os.environ.get('DOCKER_HOST', '') not in {'', 'unix:///var/run/docker.sock'}:
        raise InstallError('v1 requires local rootful Docker at /var/run/docker.sock. Remote/rootless contexts are unsupported.')
    if any('rootless' in x for x in info.get('SecurityOptions', [])):
        raise InstallError('Use a local rootful Docker daemon; rootless GPU deployment is unsupported in v1.')
    drivers = runner(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader']).splitlines()
    if not drivers:
        raise InstallError('No NVIDIA GPU/driver was detected by nvidia-smi.')
    if env.get('DEPLOYMENT_MODE', 'managed') == 'managed' and any(tuple(map(int, line.strip().split('.'))) < (570, 124, 6) for line in drivers):
        raise InstallError('NVIDIA driver 570.124.06+ is required by CUDA 12.8.1. Update the host driver and reboot.')
    if disk(ROOT).free < MIN_FREE:
        raise InstallError('At least 30 GiB free is required for images/build cache/models. Free space and retry.')
    if not os.access(ROOT, os.W_OK):
        raise InstallError('Repository is not writable. Clone into a directory owned by your current user.')
    print('Checking NVIDIA Container Toolkit with a temporary official GPU container; no models are loaded.', flush=True)
    probe_image = GPU_IMAGE if env.get('DEPLOYMENT_MODE', 'managed') == 'managed' else 'ubuntu:24.04'
    try:
        runner(['docker','run','--rm','--gpus','all',probe_image,'nvidia-smi'], timeout=300)
    except InstallError as exc:
        raise InstallError(f'GPU container probe failed. Configure NVIDIA Container Toolkit for Docker, restart Docker, and retry. {exc}')
    # Probe free space on the actual Docker storage filesystem without host-root traversal.
    available = runner(['docker','run','--rm','--network','none',probe_image,'df','-B1','--output=avail','/'])
    if int(available.strip().splitlines()[-1]) < MIN_FREE:
        raise InstallError('Docker storage has less than 30 GiB free. Free image/build cache space or expand Docker storage.')
    print('Docker, Compose, local daemon, GPU driver/toolkit, permissions, and disk checks passed.', flush=True)


def configure(path, env):
    if path.is_symlink():
        raise InstallError('Refusing to modify a symlinked .env file.')
    before = path.read_text() if path.exists() else ''
    changes = {}
    defaults = {'DEPLOYMENT_MODE':'managed', 'STATION_INSTANCE':'audio-station',
                'BIND_ADDRESS':'127.0.0.1', 'CONTROLLER_PORT':'8080', 'APPLIO_PORT':'6969'}
    for key, value in defaults.items():
        if key not in env:
            changes[key] = value
    if not env.get('GATEWAY_TOKEN'):
        changes['GATEWAY_TOKEN'] = secrets.token_hex(32)
        before = re.sub(r'^GATEWAY_TOKEN\s*=.*\n?', '', before, flags=re.M)
    if not env.get('WORKLOAD_NETWORK') and env.get('STATION_INSTANCE', 'audio-station') != 'audio-station':
        changes['WORKLOAD_NETWORK'] = env['STATION_INSTANCE'] + '-workloads'
    if not env.get('APPLIO_PUBLIC_URL'):
        changes['APPLIO_PUBLIC_URL'] = f"http://localhost:{env.get('APPLIO_PORT', '6969')}"
    if changes:
        content = before.rstrip() + '\n' + ''.join(f'{key}={value}\n' for key, value in changes.items())
        temporary = path.with_name('.env.station-new')
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(content)
        os.replace(temporary, path)
    path.chmod(0o600)
    return read_env(path)


def volumes(env, runner=run):
    instance = env.get('STATION_INSTANCE', 'audio-station')
    for suffix, override in [('data','HOST_DATA_DIR'), ('state',None), ('input','HOST_INPUT_DIR'),
                             ('output','HOST_OUTPUT_DIR'), ('models','HOST_MODELS_DIR'),
                             ('applio-models',None), ('applio-assets',None), ('applio-logs',None), ('applio-cache',None)]:
        if override and env.get(override):
            value = env[override]
            if value.startswith('/'):
                if not Path(value).is_dir():
                    raise InstallError(f'{override} must name an existing directory. No directory was created or changed.')
            else:
                runner(['docker','volume','inspect',value])
            continue
        name = instance + '-' + suffix
        try:
            metadata = json.loads(runner(['docker','volume','inspect',name]))[0]
        except InstallError as exc:
            # Only a missing volume permits creation. A daemon/permission failure does not.
            if not any(word in str(exc).lower() for word in ['no such volume', 'not found']):
                raise
            metadata = None
        if metadata:
            labels = metadata.get('Labels') or {}
            if labels.get('io.audio-station.managed') != instance:
                raise InstallError(f'Volume {name} already exists without ownership labels. Set an explicit HOST_* override or use another STATION_INSTANCE; contents were preserved.')
        else:
            logical = suffix if suffix.startswith('applio-') else 'station-' + suffix
            runner(['docker','volume','create','--label',f'io.audio-station.managed={instance}',
                    '--label',f'com.docker.compose.project={instance}',
                    '--label',f'com.docker.compose.volume={logical}',name])
        if suffix in {'data','input','output'}:
            runner(['docker','run','--rm','--network','none','-v',name+':/volume',
                    'python:3.12.9-slim-bookworm','python','-c',
                    'import os; p="/volume"; owner=os.stat(p).st_uid; '
                    'assert owner==10001 or not os.listdir(p), "Existing nonempty volume has different owner; resolve permissions manually"; '
                    'os.chown(p,10001,10001) if owner!=10001 else None'], timeout=300)


def main():
    parser = argparse.ArgumentParser(description='Install/update Audio Station without launching AI workloads')
    parser.add_argument('--check', action='store_true', help='Validate only (the official GPU probe image may be pulled)')
    args = parser.parse_args()
    try:
        env = read_env(ROOT / '.env')
        preflight(env)
        if args.check:
            return 0
        env = configure(ROOT / '.env', env)
        volumes(env)
        run(['docker','compose','config','--quiet'])
        run(['docker','compose','up','-d','--build','--wait','--wait-timeout','180','controller','gateway'], capture=False, timeout=1800)
        print(f"Open http://localhost:{env.get('CONTROLLER_PORT','8080')} and install tools in Setup. AI workloads remain stopped.")
        return 0
    except (InstallError, ValueError, KeyError, OSError) as exc:
        print(f'ERROR: {exc}\nSee docs/troubleshooting.md. Existing models/workload containers were not replaced.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
