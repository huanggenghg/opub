"""Keep publish histories created by integration tests out of user data."""
import pytest


@pytest.fixture(autouse=True)
def isolated_publish_history(tmp_path, monkeypatch):
    monkeypatch.setattr('publish.history.BASE_DIR', tmp_path / 'history-data')
