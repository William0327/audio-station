import hashlib
from types import SimpleNamespace
import httpx
import pytest
from controller import model_manager as models
from controller import settings as s


@pytest.fixture
def catalogue(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'MODELS',tmp_path/'models')
    s.MODELS.mkdir()
    content=b'approved-test-model'
    entry={'title':'Test','tool':'separator','files':[{'path':'test.onnx','size':len(content),'url':'https://publisher.example/model','sha256':hashlib.sha256(content).hexdigest()}]}
    monkeypatch.setattr(models,'CATALOG',{'approved':entry})
    return entry,content


def transport(monkeypatch,content):
    original=httpx.Client
    monkeypatch.setattr(models.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=content)),**kwargs))


def test_checksums_progress_and_idempotent_cache(catalogue,monkeypatch):
    _,content=catalogue
    transport(monkeypatch,content)
    progress=[]
    models.install('approved',lambda message,value:progress.append(value))
    assert (s.MODELS/'test.onnx').read_bytes()==content
    assert progress[-1]==100
    models.install('approved',lambda *args:None)
    assert (s.MODELS/'test.onnx').read_bytes()==content
    assert not list(s.MODELS.glob('*.station-part'))


def test_corrupt_download_is_discarded(catalogue,monkeypatch):
    _,content=catalogue
    transport(monkeypatch,b'x'*len(content))
    with pytest.raises(RuntimeError,match='checksum'):
        models.install('approved',lambda *args:None)
    assert list(s.MODELS.iterdir())==[]


def test_existing_models_never_overwritten_or_deleted(catalogue):
    (s.MODELS/'test.onnx').write_bytes(b'custom model')
    (s.MODELS/'other.onnx').write_bytes(b'another model')
    with pytest.raises(RuntimeError,match='refusing to overwrite'):
        models.install('approved',lambda *args:None)
    with pytest.raises(RuntimeError,match='refusing to delete'):
        models.remove('approved',lambda *args:None)
    assert (s.MODELS/'test.onnx').read_bytes()==b'custom model'
    assert (s.MODELS/'other.onnx').read_bytes()==b'another model'


def test_delete_is_limited_to_verified_catalogue_files(catalogue):
    _,content=catalogue
    (s.MODELS/'test.onnx').write_bytes(content)
    (s.MODELS/'other.onnx').write_bytes(b'keep')
    models.remove('approved',lambda *args:None)
    assert not (s.MODELS/'test.onnx').exists()
    assert (s.MODELS/'other.onnx').read_bytes()==b'keep'


def test_low_disk_preserves_models(catalogue,monkeypatch):
    monkeypatch.setattr(models.shutil,'disk_usage',lambda path:SimpleNamespace(free=1))
    with pytest.raises(RuntimeError,match='space'):
        models.install('approved',lambda *args:None)
