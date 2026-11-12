"""Private CLI: import complements, DB reconstruction, one fit, DB inference.

No normal API startup imports this module; there are no public upload routes.
Every mutating action is explicit. Ingestion never calls train/infer.
"""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys

from sigard_ml.ingestion.epidemiology.db import connect,migrate
from sigard_ml.ingestion.epidemiology.complementary import OpenMeteoCSV,PublicDengueCSV,CensusCSV,import_complement
from sigard_ml.forecasting.core_data import read_records,proposed_coverage,materialize_dataset,canonical_hash
from sigard_ml.forecasting.core_model import PROTOCOL,train_and_register,infer
from sigard_ml.forecasting.inventory import build_inventory,digest

ROOT=Path(__file__).resolve().parents[4]
PRIVATE=ROOT/'data/interim/official'
ADAPTERS={x.name:x for x in (OpenMeteoCSV(),PublicDengueCSV(),CensusCSV())}


def private_new(path):
    resolved=Path(path).resolve()
    if not resolved.is_relative_to(PRIVATE) or resolved.exists():raise ValueError('new_private_output_required')
    resolved.parent.mkdir(parents=True,exist_ok=True)
    return resolved


def write(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,default=str,allow_nan=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inventory','prepare','propose-coverage','materialize','train','infer'])
    parser.add_argument('--connection',required=True)
    parser.add_argument('--config',required=True)
    parser.add_argument('--report',required=True)
    parser.add_argument('--origin')
    parser.add_argument('--mode',choices=['operational','retrospective'],default='operational')
    parser.add_argument('--historical-reproduction',action='store_true')
    args=parser.parse_args()
    if args.action in ('train','infer') and not args.historical_reproduction:
        parser.error('Archived Poisson core: use the frozen final h1 results; explicit reproduction required')
    try:
        output=private_new(args.report)
        connection=Path(args.connection).resolve();config_path=Path(args.config).resolve()
        if not connection.is_relative_to(PRIVATE) or not config_path.is_relative_to(PRIVATE):raise ValueError('private_configuration_required')
        cfg=json.loads(config_path.read_text(encoding='utf-8-sig'))
        if cfg.get('status')!='approved' or not cfg.get('authorization_ref'):raise ValueError('explicit_run_authorization_required')
        os.environ['SIGARD_EPI_DATABASE_URL']=json.loads(connection.read_text(encoding='utf-8-sig'))['url']
        if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()!='entrenamiento-ML':raise ValueError('wrong_branch')
        if args.action=='prepare':migrate()
        with connect() as conn:
            if args.action=='inventory':
                result=build_inventory(ROOT,conn,output)
                print(json.dumps(dict(status='complete',**result)));return 0
            if args.action=='prepare':
                results=[]
                for entry in cfg['complementary_sources']:
                    path=(ROOT/entry['path']).resolve()
                    if not path.is_relative_to(ROOT/'data'):raise ValueError('source_outside_data')
                    results.append(import_complement(conn,path,ADAPTERS[entry['adapter']],expected_sha256=entry['sha256'],
                        version=entry['version'],authorization_ref=cfg['authorization_ref']))
                result=dict(imports=results,no_sisa_reimport=True,no_training=True)
            elif args.action=='propose-coverage':
                records=read_records(conn,resolution_version=cfg['resolution_version'],batch_ids=cfg['batch_ids'])
                result=dict(covered_weeks=list(map(str,proposed_coverage(records))),
                    policy='experimental support envelope of filtered dated records; never verified completeness',
                    confirmation='adopt only through explicit materialization config; conservative counts remain NULL')
            elif args.action=='materialize':
                result=materialize_dataset(conn,version=cfg['dataset_version'],resolution_version=cfg['resolution_version'],
                    batch_ids=cfg['batch_ids'],climate_batch_id=cfg['climate_batch_id'],
                    complementary_batch_ids=cfg.get('complementary_batch_ids',[]),
                    covered_weeks=[date.fromisoformat(x) for x in cfg['covered_weeks']],authorization_ref=cfg['authorization_ref'])
            elif args.action=='train':
                frozen=output.parent/'protocol-before-fit.private.json'
                code={p.relative_to(ROOT).as_posix():digest(p) for p in
                    [*Path(__file__).parent.glob('core_*.py'),Path(__file__).parent/'v3.py',Path(__file__).parent/'v2.py']}
                write(frozen,dict(protocol=PROTOCOL,protocol_sha256=canonical_hash(PROTOCOL),
                    code_sha256=code,git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    dirty_worktree=True,authorization_ref=cfg['authorization_ref'],python=sys.version))
                result,predictions,panel,payload=train_and_register(conn,dataset_version=cfg['dataset_version'],
                    model_version=cfg['model_version'],protocol_sha256=canonical_hash(PROTOCOL))
                predictions.to_csv(output.parent/'evaluation-predictions.private.csv',index=False)
                panel.to_parquet(output.parent/'modeling-panel.private.parquet',index=False)
                (output.parent/'candidate.private.joblib').write_bytes(payload)
                result['reproducibility']=dict(code_sha256=code,protocol_file_sha256=digest(frozen))
            else:
                if not args.origin:raise ValueError('explicit_origin_required')
                result=infer(conn,model_version=cfg['model_version'],origin=date.fromisoformat(args.origin),mode=args.mode)
        write(output,result)
        print(json.dumps(dict(status='complete',action=args.action,private_report_written=True,
            model_state=result.get('state'),prediction_status=result.get('status'))));return 0
    except Exception as error:
        # Values, SQL exceptions and credentials never reach logs.
        print(json.dumps(dict(status='blocked_or_failed',action=args.action,error_type=type(error).__name__,
            reason='inspect_private_configuration_and_reviewed_contract')),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
