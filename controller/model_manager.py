import hashlib
import os
import shutil
from pathlib import Path

import httpx
from fastapi import HTTPException
from controller import settings as s
from controller.catalog import CATALOG


def root_for(entry):
    return s.MODELS if entry['tool'] == 'separator' else s.APPLIO_MODELS


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def target(root, name):
    raw = root / name
    if raw.is_symlink() or any(p.is_symlink() for p in raw.parents if p != root.parent):
        raise HTTPException(409, 'Refusing a symlink in the model cache')
    return s.contained(root, name)


def listing():
    result = []
    for id, entry in CATALOG.items():
        root = root_for(entry)
        installed = all(target(root, f['path']).is_file() for f in entry['files'])
        result.append({k: v for k, v in entry.items() if k != 'files'} | {
            'id': id, 'installed': installed, 'size': sum(f['size'] for f in entry['files']),
            'checksums': all(bool(f.get('sha256')) for f in entry['files'])})
    return result


def install(id, progress):
    entry = CATALOG[id]
    root = root_for(entry)
    root.mkdir(parents=True, exist_ok=True)
    needed = sum(f['size'] for f in entry['files'] if not target(root, f['path']).exists())
    if shutil.disk_usage(root).free < needed + 512 * 1024 * 1024:
        raise RuntimeError('Insufficient model-cache space. Free space and retry; existing models were preserved.')
    total = sum(f['size'] for f in entry['files'])
    completed = 0
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30, read=60)) as client:
        for spec in entry['files']:
            path = target(root, spec['path'])
            if path.exists():
                progress(f"Verifying existing {spec['path']}", int(completed / total * 100))
                if spec.get('sha256') and digest(path) != spec['sha256']:
                    raise RuntimeError(f"Existing {spec['path']} differs from catalogue checksum; refusing to overwrite. Back it up and resolve manually.")
                completed += spec['size']
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(path.name + '.station-part')
            # 'x' prevents overwriting partials or user files from a prior attempt.
            if partial.exists():
                raise RuntimeError(f"Incomplete download {partial.name} exists; inspect/remove only this partial file, then retry.")
            received = 0
            hasher = hashlib.sha256()
            created = False
            try:
                with partial.open('xb') as handle:
                    created = True
                    with client.stream('GET', spec['url']) as response:
                        response.raise_for_status()
                        for chunk in response.iter_bytes(1024 * 1024):
                            received += len(chunk)
                            if received > spec['size']:
                                raise RuntimeError('Publisher asset exceeds reviewed size; update catalogue before downloading')
                            handle.write(chunk)
                            hasher.update(chunk)
                            progress(f"Downloading {spec['path']} ({received // 1024 // 1024} MB)", int((completed + received) / total * 100))
                if received != spec['size'] or (spec.get('sha256') and hasher.hexdigest() != spec['sha256']):
                    raise RuntimeError('Model checksum or size mismatch; download discarded')
                # Hard-link commits atomically without ever overwriting an existing file.
                os.link(partial, path)
                partial.unlink()
                completed += received
            except BaseException:
                if created:
                    partial.unlink(missing_ok=True)
                raise
    progress('Installed; checksums verified. Workload remains stopped.', 100)


def remove(id, progress):
    entry = CATALOG[id]
    root = root_for(entry)
    for spec in entry['files']:
        path = target(root, spec['path'])
        # Never remove directories, unlisted files, or a different user-supplied model.
        if path.exists() and (not spec.get('sha256') or digest(path) != spec['sha256']):
            raise RuntimeError('Model differs from catalogue; refusing to delete an existing custom file')
    for spec in entry['files']:
        target(root, spec['path']).unlink(missing_ok=True)
    progress('Catalogue model files removed; other caches preserved.', 100)
