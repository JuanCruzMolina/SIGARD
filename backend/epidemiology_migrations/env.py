import os
from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

url=os.environ.get('SIGARD_EPI_DATABASE_URL','')
parsed=make_url(url)
if parsed.get_backend_name()!='postgresql' or parsed.host not in ('127.0.0.1','localhost') or parsed.port in (None,5432):
    raise ValueError('Explicit private loopback PostgreSQL port required; 5432 prohibited')
if not parsed.database or not parsed.database.startswith('sigard_epi_'):
    raise ValueError('Dedicated or explicitly provisioned sigard_epi_ database required')
if context.is_offline_mode():
    context.configure(url=url,literal_binds=True,version_table='schema_version',version_table_schema='ingestion')
    with context.begin_transaction():context.run_migrations()
else:
    with create_engine(url,poolclass=pool.NullPool,hide_parameters=True).connect() as connection:
        if not connection.exec_driver_sql('SHOW cluster_name').scalar().startswith('sigard-epi-'):
            raise ValueError('Migrations require explicitly owned private cluster')
        connection.exec_driver_sql('CREATE SCHEMA IF NOT EXISTS ingestion')
        connection.commit()
        context.configure(connection=connection,version_table='schema_version',version_table_schema='ingestion')
        with context.begin_transaction():context.run_migrations()
