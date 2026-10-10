import os
from pathlib import Path

DATA = Path(os.getenv('DATA_DIR', './data')).resolve()
INPUT = Path(os.getenv('INPUT_DIR', './input')).resolve()
OUTPUT = Path(os.getenv('OUTPUT_DIR', './output')).resolve()
MODELS = Path(os.getenv('MODELS_DIR', './models')).resolve()
APPLIO_MODELS = Path(os.getenv('APPLIO_MODELS_DIR', './data/applio-models')).resolve()
STATE = Path(os.getenv('STATE_DIR', './data/gateway')).resolve()
DEPLOYMENT_MODE = os.getenv('DEPLOYMENT_MODE', 'managed')
GATEWAY = os.getenv('GATEWAY_URL', 'http://gateway:8081')
TOKEN = os.getenv('GATEWAY_TOKEN', '')
MAX_UPLOAD = int(os.getenv('MAX_UPLOAD_MB', '500')) * 1024 * 1024
APPLIO_URL = os.getenv('APPLIO_PUBLIC_URL', 'http://localhost:6969')
EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.aiff'}

def installed_models():
    return sorted(p.name for p in MODELS.iterdir() if p.is_file() and not p.is_symlink()
                  and p.suffix.lower() in {'.onnx', '.pth', '.pt', '.ckpt', '.yaml', '.yml'})

def contained(root, *parts):
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Invalid file path')
    return path
