"""Voice assets are opaque user files. Never deserialize a model in the controller."""
import hashlib
import os
import shutil
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict
from controller import settings as s


class ConversionOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    index: str = Field(default='', max_length=512)
    pitch: int = Field(default=0, ge=-24, le=24)
    index_rate: float = Field(default=0.75, ge=0, le=1)
    protect: float = Field(default=0.33, ge=0, le=0.5)
    volume_envelope: float = Field(default=1, ge=0, le=1)
    f0_method: Literal['rmvpe', 'fcpe'] = 'rmvpe'


class VoiceImport(BaseModel):
    id: str = Field(pattern=r'^[0-9a-f]{32}$')
    filename: str = Field(min_length=1, max_length=180)
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def asset_path(name, suffix):
    try:
        path = s.contained(s.VOICES, name)
    except ValueError:
        raise HTTPException(422, 'Invalid voice asset')
    raw = s.VOICES / name
    if (not name or raw.is_symlink() or any(p.is_symlink() for p in raw.parents if p != s.VOICES.parent)
            or path.suffix.lower() != suffix or not path.is_file()):
        raise HTTPException(422, 'Choose an installed voice model/index')
    return path


def listing():
    result = {'models': [], 'indexes': []}
    if s.VOICES.exists():
        # os.walk does not follow symlink directories.
        for root, _, files in os.walk(s.VOICES):
            for filename in sorted(files):
                path = Path(root) / filename
                suffix = path.suffix.lower()
                if suffix not in {'.pth', '.index'} or filename.startswith(('G_', 'D_', '.')):
                    continue
                name = path.relative_to(s.VOICES).as_posix()
                try:
                    asset_path(name, suffix)
                except HTTPException:
                    continue
                result['models' if suffix == '.pth' else 'indexes'].append(
                    {'id': name, 'name': filename, 'size': path.stat().st_size})
    for values in result.values():
        values.sort(key=lambda x: x['id'])
    return result


def commit_import(item):
    filename = item.filename
    if (Path(filename).name != filename or '\\' in filename or filename.startswith('.')
            or filename.startswith(('G_','D_'))
            or Path(filename).suffix.lower() not in {'.pth', '.index'} or '\x00' in filename):
        raise HTTPException(422, 'Import a .pth voice model or .index file')
    if item.size > s.MAX_VOICE_IMPORT:
        raise HTTPException(413, 'Voice asset exceeds import limit')
    source = s.contained(s.INPUT, 'voice-imports', item.id, 'asset')
    if not source.is_file() or source.is_symlink() or source.stat().st_size != item.size:
        raise HTTPException(422, 'Staged voice asset is missing or incomplete')
    s.VOICES.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(s.VOICES).free < item.size + 64 * 1024 * 1024:
        raise HTTPException(507, 'Insufficient space for voice import')
    directory = s.contained(s.VOICES, 'audio-station-imports', item.id)
    directory.mkdir(parents=True, exist_ok=False)
    destination = directory / filename
    partial = directory / '.upload'
    digest = hashlib.sha256()
    try:
        with source.open('rb') as incoming, partial.open('xb') as outgoing:
            for chunk in iter(lambda: incoming.read(1024 * 1024), b''):
                digest.update(chunk)
                outgoing.write(chunk)
        if digest.hexdigest() != item.sha256:
            raise HTTPException(422, 'Voice asset checksum mismatch')
        os.link(partial, destination)
        partial.unlink()
    except BaseException:
        partial.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return {'id': destination.relative_to(s.VOICES).as_posix(), 'name': filename,
            'size': item.size, 'sha256': item.sha256}
