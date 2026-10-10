import pytest
from controller import settings as s
from controller import adapters


@pytest.fixture(autouse=True)
def isolated_gateway_state(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'STATE', tmp_path / 'gateway-state')
    monkeypatch.setattr(s, 'APPLIO_MODELS', tmp_path / 'applio-models')
    # Original controller tests exercise external compatibility; managed tests opt in.
    monkeypatch.setattr(adapters, 'MODE', 'external')
