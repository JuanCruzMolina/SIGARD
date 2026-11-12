"""Private explicit Option B actions. Configuration is JSON; all model data are SQL."""
import argparse
from datetime import date
import json
from pathlib import Path
import subprocess

from sigard_ml.data_access import MLRepository,DatasetBlocked
from sigard_ml.data_access.tabular_guard import forbid_tabular_reads
from sigard_ml.forecasting.core_pipeline import ROOT,PRIVATE,private_new,write
from sigard_ml.forecasting.option_b_training import PROTOCOL,train,infer
from sigard_ml.forecasting.option_b_data import materialize
from sigard_ml.ingestion.epidemiology.db import connect,migrate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','inspect','train','infer'])
    parser.add_argument('--connection',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--family',choices=['A','B','V3'])
    parser.add_argument('--dataset-version')
    parser.add_argument('--model-version')
    parser.add_argument('--horizon',type=int,choices=[1,2,4],default=1)
    parser.add_argument('--origin')
    parser.add_argument('--mode',choices=['retrospective','operational'],default='retrospective')
    args=parser.parse_args()
    try:
        if subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()!='entrenamiento-ML':
            raise DatasetBlocked('wrong_branch')
        if any(not p.resolve().is_relative_to(PRIVATE) for p in (args.connection,args.config)):
            raise DatasetBlocked('private_configuration_required')
        cfg=json.loads(args.config.read_text(encoding='utf-8-sig'))
        if cfg.get('status')!='approved' or not cfg.get('authorization_ref'):
            raise DatasetBlocked('explicit_project_research_configuration_required')
        output=private_new(args.report)
        url=json.loads(args.connection.read_text(encoding='utf-8-sig'))['url']
        if args.action=='prepare':
            migrate(url)  # additive schema only; not an import or a fit
        with connect(url) as conn,forbid_tabular_reads():
            if args.action=='prepare':
                result=materialize(conn,version=cfg['scenario_version'],resolution_version=cfg['resolution_version'],
                    batch_ids=cfg['batch_ids'],climate_batch_id=cfg['climate_batch_id'],protocol=PROTOCOL,
                    authorization_ref=cfg['authorization_ref'],today=date.today())
            elif args.action=='train':
                if cfg.get('research_training_authorized') is not True or not all((args.dataset_version,args.family,args.model_version)):
                    raise DatasetBlocked('explicit_dataset_model_family_and_training_permission_required')
                result=train(conn,dataset_version=args.dataset_version,family=args.family,model_version=args.model_version,horizon=args.horizon)
            elif args.action=='infer':
                if not args.model_version or not args.origin:
                    raise DatasetBlocked('explicit_model_version_and_origin_required')
                result=infer(conn,model_version=args.model_version,origin=date.fromisoformat(args.origin),mode=args.mode)
            else:
                if not args.dataset_version or not args.family:
                    raise DatasetBlocked('explicit_dataset_and_family_required')
                frame=MLRepository(conn).research_frame(args.family,args.dataset_version,horizon=args.horizon)
                result=dict(status='inspected',rows=len(frame),data_source='postgresql',training_performed=False)
        write(output,result)
        print(json.dumps(dict(status=result.get('status','complete'),action=args.action,private_report_written=True)))
        return 0
    except Exception as error:
        reason=str(error) if isinstance(error,DatasetBlocked) else 'inspect_private_research_contract'
        print(json.dumps(dict(status='failed_or_blocked',action=args.action,reason=reason)))
        return 1


if __name__=='__main__':raise SystemExit(main())
