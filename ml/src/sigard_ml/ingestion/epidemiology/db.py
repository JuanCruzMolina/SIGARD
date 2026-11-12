"""Explicit private PostgreSQL connection; no API settings or dotenv imports."""
from contextlib import contextmanager
import os
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

def connection_url(url=None):
    parsed=make_url(url or os.environ.get('SIGARD_EPI_DATABASE_URL',''))
    if (parsed.get_backend_name()!='postgresql' or parsed.host not in ('127.0.0.1','localhost')
            or parsed.port in (None,5432) or not parsed.database or not parsed.database.startswith('sigard_epi_')
            or parsed.query):
        raise ValueError('explicit_private_database_required')
    return parsed

@contextmanager
def connect(url=None):
    p=connection_url(url)
    conn=psycopg2.connect(host=p.host,port=p.port,dbname=p.database,user=p.username,password=p.password,connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('SHOW cluster_name')
            if not cur.fetchone()[0].startswith('sigard-epi-'):raise ValueError('cluster_not_owned')
        conn.rollback()
        yield conn
    finally:conn.close()

def get_id(cur,table,values,keys=None):
    """Only internal table/column identifiers; all cell values use bind parameters."""
    keys=keys or list(values)
    schema,name=table.split('.')
    query=sql.SQL('INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING RETURNING id').format(
        sql.Identifier(schema),sql.Identifier(name),sql.SQL(',').join(map(sql.Identifier,values)),sql.SQL(',').join(sql.Placeholder() for _ in values))
    cur.execute(query,list(values.values()));row=cur.fetchone()
    if row:return row[0]
    where=sql.SQL(' AND ').join(sql.SQL('{} IS NOT DISTINCT FROM %s').format(sql.Identifier(k)) for k in keys)
    cur.execute(sql.SQL('SELECT id FROM {}.{} WHERE {}').format(sql.Identifier(schema),sql.Identifier(name),where),[values[k] for k in keys])
    row=cur.fetchone()
    if not row:raise ValueError('catalog_conflict')
    return row[0]

def migrate(url=None):
    from alembic.config import Config
    from alembic import command
    p=connection_url(url)
    with connect(p.render_as_string(hide_password=False)):pass
    root=Path(__file__).resolve().parents[5]
    config=Config(str(root/'backend/alembic-epidemiology.ini'))
    old=os.environ.get('SIGARD_EPI_DATABASE_URL')
    os.environ['SIGARD_EPI_DATABASE_URL']=p.render_as_string(hide_password=False)
    try:command.upgrade(config,'head')
    finally:
        if old is None:os.environ.pop('SIGARD_EPI_DATABASE_URL',None)
        else:os.environ['SIGARD_EPI_DATABASE_URL']=old
