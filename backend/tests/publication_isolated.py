"""Run fictitious publication tests without dotenv, PostgreSQL or Docker.

From repository root: backend/.venv/Scripts/python.exe -B
backend/tests/publication_isolated.py [--backend-regression].
"""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

root = Path(__file__).resolve().parents[2]
os.chdir(root)
sys.path.insert(0, str(root / 'backend'))
for key in list(os.environ):
    if key.startswith(('PG', 'SIGARD_POSTGIS')) or key in (
        'DATABASE_URL', 'SIGARD_TEST_POSTGRES_URL', 'ADMIN_BOOTSTRAP_EMAIL', 'ADMIN_BOOTSTRAP_PASSWORD',
    ):
        os.environ.pop(key, None)
os.environ.update(SECRET_KEY='fictitious-territorial-import-test-secret-key', DATABASE_URL='sqlite:///:memory:')
from app.config import Settings, get_settings
Settings.model_config['env_file'] = None
get_settings.cache_clear()

from sqlalchemy import event
from sqlalchemy.engine import Engine
@event.listens_for(Engine, 'do_connect')
def sqlite_only(dialect, _record, _args, _params):
    if dialect.name != 'sqlite':
        raise RuntimeError('Non-SQLite database connection forbidden in this review')

original_popen = subprocess.Popen
def no_docker(args, *extra, **kwargs):
    executable = str(args[0] if isinstance(args, (list, tuple)) else args).lower()
    if 'docker' in executable:
        raise RuntimeError('Docker forbidden in this review')
    return original_popen(args, *extra, **kwargs)
subprocess.Popen = no_docker

import pytest
selection = ['backend/tests'] if '--backend-regression' in sys.argv else ['backend/tests/test_publication_import.py']
label = 'backend' if '--backend-regression' in sys.argv else 'importer'
output = root / '.tmp/territorial-import-review'
output.mkdir(parents=True, exist_ok=True)
# Keep fixture paths below Windows/Arrow path limits in a nested checkout.
# Never reuse a previous directory: pytest may clean its selected basetemp.
basetemp = root / '.tmp' / f'p-{uuid4().hex[:12]}'
if basetemp.exists():
    raise RuntimeError('Test temporary directory already exists')
raise SystemExit(pytest.main(selection + ['-q', '-p', 'no:cacheprovider', '--tb=short',
    '--basetemp', str(basetemp),
    '--junitxml', str(output / f'{label}.xml')]))
