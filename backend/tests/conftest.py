import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-enough-entropy")
os.environ.setdefault("REPORT_RATE_LIMIT", "100")
os.environ.setdefault("GEOCODING_RATE_LIMIT", "100")
os.environ.setdefault("ADMIN_LOGIN_RATE_LIMIT", "100")

from app.database import Base  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    app = create_app(database_url=database_url, auto_create_schema=True)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(app.state.engine)
