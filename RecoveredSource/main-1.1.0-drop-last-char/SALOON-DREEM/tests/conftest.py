from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_PATH", str(data_dir / "test.db"))
    monkeypatch.setenv("TOKEN_SECRET", "test-only-secret-never-use-in-production")
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Gaza")
    monkeypatch.setenv("CORS_ORIGINS", "")
    module_name = "backend.app.main"
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        module = importlib.import_module(module_name)
    with TestClient(module.app) as test_client:
        yield test_client
