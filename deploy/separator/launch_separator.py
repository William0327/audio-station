"""Run the installed CLI without permitting implicit model downloads."""
import sys
from pathlib import Path
from contextlib import contextmanager
from tempfile import TemporaryDirectory
import requests

# CLI metadata requests are allowed; missing model-weight downloads are refused.
# A read-only /models mount is the additional enforcement boundary.
original = requests.sessions.Session.request
def metadata_only(self, method, url, **kwargs):
    from urllib.parse import urlsplit
    if Path(urlsplit(url).path).suffix.lower() in {'.onnx', '.pth', '.pt', '.ckpt', '.bin', '.yaml', '.yml'}:
        raise RuntimeError('Implicit model download disabled. Install this model in Audio Station first.')
    return original(self, method, url, **kwargs)

@contextmanager
def writable_model_view(source):
    """Keep weights in their read-only volume; write upstream metadata elsewhere."""
    with TemporaryDirectory(prefix='station-models-') as directory:
        destination = Path(directory)
        for entry in Path(source).iterdir():
            if entry.is_file():
                (destination / entry.name).symlink_to(entry.resolve())
        yield destination


def main():
    import os
    from audio_separator.utils.cli import main as cli
    args = sys.argv
    index = args.index('--model_file_dir') + 1
    source = args[index]
    previous_model_dir = os.environ.get('AUDIO_SEPARATOR_MODEL_DIR')
    with writable_model_view(source) as directory:
        args[index] = str(directory)
        os.environ['AUDIO_SEPARATOR_MODEL_DIR'] = str(directory)
        requests.sessions.Session.request = metadata_only
        try:
            cli()
        finally:
            requests.sessions.Session.request = original
            args[index] = source
            if previous_model_dir is None:
                os.environ.pop('AUDIO_SEPARATOR_MODEL_DIR', None)
            else:
                os.environ['AUDIO_SEPARATOR_MODEL_DIR'] = previous_model_dir


if __name__ == '__main__':
    main()
