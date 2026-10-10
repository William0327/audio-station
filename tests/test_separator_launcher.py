import runpy
import os
from pathlib import Path

import pytest


launcher = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'deploy/separator/launch_separator.py'))


def test_metadata_is_writable_without_modifying_stored_models(tmp_path):
    models = tmp_path / 'models'
    models.mkdir()
    weight = models / 'example.onnx'
    weight.write_bytes(b'existing model')
    if os.name == 'nt':
        probe = tmp_path / 'symlink-probe'
        try:
            probe.symlink_to(weight)
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 1314:
                pytest.skip('Windows requires symlink privileges; Linux CI runs this test')
            raise
        probe.unlink()
    with launcher['writable_model_view'](models) as view:
        assert (view / weight.name).is_symlink()
        assert (view / weight.name).read_bytes() == b'existing model'
        (view / 'download_checks.json').write_text('{}')
        assert not (models / 'download_checks.json').exists()
    assert not view.exists()
    assert weight.read_bytes() == b'existing model'


@pytest.mark.parametrize('extension', ['onnx','pth','yaml'])
def test_implicit_model_downloads_remain_blocked(extension):
    with pytest.raises(RuntimeError, match='Implicit model download disabled'):
        launcher['metadata_only'](None, 'GET', f'https://example.invalid/model.{extension}')
