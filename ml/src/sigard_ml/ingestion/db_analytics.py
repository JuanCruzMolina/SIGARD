"""Explicit DB-only analytical runs; never fits or activates an estimator."""
import argparse,json,sys
from datetime import date,datetime
from pathlib import Path
from sigard_ml.ingestion.db_import import private_output
from sigard_ml.ingestion.epidemiology.db import connect,get_id
from sigard_ml.ingestion.epidemiology.analytics import materialize,seed_policies,declare_coverage

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True,help='Reviewed private analytical/coverage contract')
    p.add_argument('--report',required=True)
    a=p.parse_args()
    try:
        output=private_output(a.report);config=json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
        if config.get('status')!='approved' or not config.get('authorization_ref'):raise ValueError('authorization_required')
        with connect() as conn:
            temporal,classification=seed_policies(conn)
            criterion=None
            if config.get('coverage_claims'):
                with conn:
                    with conn.cursor() as cur:
                        criterion=get_id(cur,'epidemiology.criterio_cobertura',dict(version=config['version']+'-coverage',politica_clasificacion_id=classification,
                            definicion_poblacion=config['population_definition'],filtro_extraccion=config['extraction_filters']))
                        cur.execute('SELECT id FROM territory.universo WHERE version=%s',(config['universe'],));universe=cur.fetchone()[0]
                        files={}
                        for claim in config['coverage_claims']:
                            cur.execute('SELECT id FROM ingestion.archivo_fuente WHERE sha256=%s',(claim['source_sha256'],))
                            found=cur.fetchone()
                            if not found:raise ValueError('coverage_source_unknown')
                            files[claim['source_sha256']]=found[0]
                for claim in config['coverage_claims']:
                    declare_coverage(conn,file_id=files[claim['source_sha256']],universe_id=universe,criterion_id=criterion,
                        start=date.fromisoformat(claim['start']),end=date.fromisoformat(claim['end']),state=claim['state'],evidence=claim['evidence'],reviewer=claim['reviewer'])
            result=materialize(conn,version=config['version'],universe_version=config['universe'],start=date.fromisoformat(config['start']),end=date.fromisoformat(config['end']),
                scenario=config.get('scenario','conservative'),coverage_weeks={date.fromisoformat(w) for w in config.get('covered_weeks',[])},
                coverage_ref=config.get('coverage_ref'),accept_provisional=config.get('accept_provisional_geography',False),
                mode=config.get('mode','retrospective'),cutoff=datetime.fromisoformat(config['cutoff']) if config.get('cutoff') else None,
                criterion_id=criterion,batch_ids=config.get('batch_ids'),climate_version=config.get('climate_version'),
                resolution_version=config.get('resolution_version'))
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(status='complete',private_report_written=True)));return 0
    except Exception:
        print(json.dumps(dict(status='blocked_or_failed',reason='check_private_run_contract')),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
