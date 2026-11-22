"""Builds the local administrative app with the predictive viewer mount, for tests.

Only generated fixtures: an isolated SQLite file, a fictitious administrator and the
generated predictive bundles of each test. Same mount as `alerts_local` (F2).
"""
import httpx

from app.config import get_settings
from app.database import Base
from app.main import create_app
from app.models import User
from app.predictive_admin import mount
from app.security import create_access_token, hash_password

BASE_URL = 'http://127.0.0.1:8767'
ORIGIN = 'http://127.0.0.1:5173'
LOCAL = {'Origin': ORIGIN, 'X-Sigard-Research': 'local-read'}


def add_account(app, email='admin@example.test', role='admin'):
    with app.state.SessionLocal() as db:
        user = User(email=email, password_hash=hash_password('fictitious-password'), rol=role)
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def bearer(user):
    return {'Authorization': 'Bearer ' + create_access_token(user, get_settings())}


def admin_app(tmp_path, service):
    """(app, trusted headers of a generated admin, that admin)."""
    app = create_app(database_url=f"sqlite:///{tmp_path / 'admin-predictive.db'}", auto_create_schema=True)
    Base.metadata.create_all(app.state.engine)
    mount(app, service)
    admin = add_account(app)
    return app, {**LOCAL, **bearer(admin)}, admin


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url=BASE_URL)
