"""Explicit loading of a hash-authorized compatible aggregate climate package."""
from datetime import date,datetime
import json,math
from .reader import digest
from .analytics import seed_policies

def load_climate(conn,path,*,expected_sha256,version):
    if digest(path)!=expected_sha256:raise ValueError('climate_hash_mismatch')
    bundle=json.loads(path.read_text(encoding='utf-8'))
    rows=bundle['climate'];seed_policies(conn);included=0
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT fuente_sha256 FROM analytics.clima_semana WHERE version=%s',(version,))
            old={r[0] for r in cur.fetchall()}
            if old and old!={expected_sha256}:raise ValueError('new_climate_source_requires_new_version')
            for row in rows:
                week=date.fromisoformat(row['week_start'])
                if week.weekday()!=6:raise ValueError('climate_not_weekly')
                cur.execute('SELECT id FROM analytics.semana_epidemiologica WHERE inicio=%s',(week,))
                found=cur.fetchone()
                if not found:raise ValueError('climate_outside_supported_calendar')
                values=[row.get(k) for k in ['temperature','humidity','precipitation']]
                compatible=bool(row.get('complete')) and all(v is not None and math.isfinite(float(v)) for v in values)
                available=datetime.fromisoformat(row['available_on']) if row.get('available_on') else None
                cur.execute('INSERT INTO analytics.clima_semana VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(version,found[0],*values,available,expected_sha256,compatible))
                included+=1
    return dict(version=version,rows=included,source_sha256=expected_sha256,as_of_unknowns_preserved=True)
