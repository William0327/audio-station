"""Run the installed CLI without permitting implicit model downloads."""
import sys
from pathlib import Path
import requests

# CLI metadata requests are allowed; missing model-weight downloads are refused.
# A read-only /models mount is the additional enforcement boundary.
original = requests.sessions.Session.request
def metadata_only(self, method, url, **kwargs):
    from urllib.parse import urlsplit
    if Path(urlsplit(url).path).suffix.lower() in {'.onnx', '.pth', '.pt', '.ckpt', '.bin', '.yaml', '.yml'}:
        raise RuntimeError('Implicit model download disabled. Install this model in Audio Station first.')
    return original(self, method, url, **kwargs)
requests.sessions.Session.request = metadata_only
from audio_separator.utils.cli import main
main()
