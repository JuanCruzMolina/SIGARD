"""Offline A/B/V3 PostgreSQL adapters; no activation of historical systems.

The consolidated core remains the only product candidate registry. These
adapters retain the historical targets, splits and estimators for explicit
research runs. Unverified equivalence blocks fitting AND prediction.
"""

from dataclasses import dataclass
from datetime import date, timedelta
import argparse
import json
from pathlib import Path

import numpy as np

from sigard_ml.data_access import DatasetBlocked, MLRepository


def dataset(repo, family, version, *, outcomes=True, origin=None, horizon=1,
            validation_start=None, test_start=None, require_equivalence=True):
    frame = repo.legacy_frame(family, version, outcomes=outcomes, origin=origin,
                             horizon=horizon, require_equivalence=require_equivalence)
    if family in ('A', 'B'):
        from sigard_ml.official.spatial_ml.research_training import PERIODS
        frame['target_end'] = frame.fecha_inicio_semana_objetivo.map(lambda d: d + timedelta(days=6))
        frame['partition'] = 'purged'
        # These target-week bounds already include the original one-week purge.
        for part, (start, end, _) in PERIODS.items():
            scope = frame.fecha_inicio_semana_objetivo.ge(start) & frame.target_end.le(end)
            frame.loc[scope, 'partition'] = part
    else:
        from sigard_ml.forecasting.training import partition
        from sigard_ml.forecasting.v2 import predictor_weeks
        frame['target_end'] = frame.target_week.map(lambda d: d + timedelta(days=6))
        support = repo.query('''SELECT radio_id,origin_week,lag_1 AS cases_lag_1,
            temperature_lag_1,humidity_lag_1,precipitation_lag_1,continuous_scope
            FROM analytics.soporte_predictor_v3 WHERE dataset_version=%s AND horizon_weeks=%s
            AND (%s::date IS NULL OR origin_week=%s)
            ORDER BY radio_id,origin_week''', (version, horizon, origin, origin))
        if support.empty:
            raise DatasetBlocked('origin_support_unavailable')
        available = predictor_weeks(support)
        continuous = support.groupby('origin_week').continuous_scope.all()
        available &= set(continuous.index[continuous])
        frame['predictor_admissible'] = frame.origin_week.isin(available)
        frame['horizon_weeks'] = horizon
        if outcomes:
            if validation_start is None or test_start is None:
                raise DatasetBlocked('explicit_frozen_temporal_boundaries_required')
            frame['partition'] = partition(frame, validation_start, test_start)
    return frame


@dataclass
class ResearchFit:
    family: str
    dataset_version: str
    horizon: int
    fit_cutoff: date
    models: object
    report: dict


def train(repo, family, version, *, training_authorized=False, horizon=1,
          validation_start=None, test_start=None):
    if training_authorized is not True:
        raise DatasetBlocked('explicit_research_training_authorization_required')
    frame = dataset(repo, family, version, horizon=horizon,
                    validation_start=validation_start, test_start=test_start)
    if frame.attrs['provenance']['modo'] != 'retrospective':
        raise DatasetBlocked('legacy_training_requires_retrospective_contract')
    if family in ('A', 'B'):
        from sigard_ml.official.spatial_ml.research_training import PERIODS, fit_models
        from sigard_ml.official.spatial_ml.research_model_b import fit_model_b
        previous_end = None
        for part, (first, last, weeks) in PERIODS.items():
            group = frame.loc[frame.partition.eq(part)]
            if (group.empty or group.fecha_inicio_semana_objetivo.min() != first
                    or group.target_end.max() != last
                    or group.fecha_inicio_semana_objetivo.nunique() != weeks
                    or set(group.objetivo_semana_siguiente.dropna().unique()) != {0, 1}
                    or (previous_end and previous_end >= group.fecha_inicio_semana.min())):
                raise DatasetBlocked('historical_temporal_design_not_reproduced')
            previous_end = last
        if family == 'A':
            models = fit_models(frame)
        else:
            estimator, _, _ = fit_model_b(frame)
            models = {'random_forest_B': estimator}
        cutoff = max(frame.loc[frame.partition.eq('train'), 'target_end'])
        report = dict(features=list(next(iter(models.values())).feature_names_in_),
                      temporal_plan='authorized_2024_only', threshold=.5)
    else:
        from sigard_ml.forecasting.v3 import validate_development_frame, fit_final
        validation = validate_development_frame(frame, horizon)
        models = fit_final(validation, horizon)
        cutoff = max(validation['development'].target_end)
        report = validation['report']
    return ResearchFit(family, version, horizon, cutoff, models,
                       dict(report, data_source='postgresql', production_enabled=False))


def predict(repo, fitted, *, origin):
    """Research-only, in-memory estimator; all predictor data come from PostgreSQL.

    Never loads an old joblib/Parquet or fits to fill missing input. No product
    route calls this function and there is no legacy registry alongside core.
    """
    if fitted.fit_cutoff >= origin:
        raise DatasetBlocked('model_not_fitted_before_origin')
    frame = dataset(repo, fitted.family, fitted.dataset_version, outcomes=False,
                    origin=origin, horizon=fitted.horizon)
    run = frame.attrs['provenance']
    if run['modo'] != 'retrospective':
        raise DatasetBlocked('legacy_operational_availability_unaccredited')
    if fitted.family in ('A', 'B'):
        from sigard_ml.official.spatial_ml.historical_expansion import ab_matrix
        from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS
        from sklearn.ensemble import RandomForestClassifier
        name = 'random_forest_' + fitted.family
        estimator = fitted.models[name]
        matrix = ab_matrix(frame, fitted.family)
        if (type(estimator) is not RandomForestClassifier or list(estimator.feature_names_in_) != list(matrix.columns)
                or list(estimator.classes_) != [0, 1]
                or any(estimator.get_params()[k] != v for k, v in RF_PARAMETERS.items())):
            raise DatasetBlocked('historical_estimator_contract_changed')
        values = estimator.predict_proba(matrix)[:, 1]
    else:
        from sigard_ml.forecasting.v3 import BASELINES
        if not frame.predictor_admissible.all():
            raise DatasetBlocked('fundamental_features_or_coverage_missing')
        selected = fitted.models['selection']['selected']
        # Migration does not promote any legacy candidate into predictions.
        if selected not in BASELINES:
            raise DatasetBlocked('legacy_candidate_not_activated')
        model = fitted.models['counts'][selected]
        if model.fit_cutoff >= origin:
            raise DatasetBlocked('model_not_fitted_before_origin')
        values = model.predict_frame(frame)
    if not np.isfinite(values).all() or (values < 0).any() or (fitted.family in ('A','B') and (values > 1).any()):
        raise DatasetBlocked('invalid_prediction')
    radio = 'radio_id' if fitted.family == 'V3' else 'radio_censal'
    return dict(status='available_private_research', dataset_version=fitted.dataset_version,
                data_source='postgresql', retrospective=True, production_enabled=False,
                origin_week=str(origin),horizon_weeks=fitted.horizon,
                target='snapshot_record_count' if fitted.family == 'V3' else 'binary_experimental_presence',
                radios=frame[radio].tolist(),values=values.tolist())


def main(family=None):
    """Inspection is read-only. A fit requires a separate explicit config flag."""
    from sigard_ml.ingestion.epidemiology.db import connect
    from sigard_ml.forecasting.core_pipeline import PRIVATE, private_new, write
    parser = argparse.ArgumentParser(description=__doc__)
    if family is None:
        parser.add_argument('--family', choices=['A', 'B', 'V3'], required=True)
    parser.add_argument('--connection', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--action', choices=['inspect', 'train'], default='inspect')
    parser.add_argument('--historical-reproduction', action='store_true')
    parser.add_argument('--mode',choices=['historical_contract','postgres_option_b'])
    args = parser.parse_args()
    if args.action == 'train' and not args.historical_reproduction:
        parser.error('Archived training: explicit historical reproduction and original authorization required')
    try:
        import subprocess
        if subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip() != 'entrenamiento-ML':
            raise DatasetBlocked('wrong_branch')
        if any(not path.resolve().is_relative_to(PRIVATE) for path in (args.connection, args.config)):
            raise DatasetBlocked('private_configuration_required')
        output = private_new(args.report)
        cfg = json.loads(args.config.read_text(encoding='utf-8-sig'))
        connection = json.loads(args.connection.read_text(encoding='utf-8-sig'))['url']
        if cfg.get('status') != 'approved' or not cfg.get('authorization_ref'):
            raise DatasetBlocked('reviewed_configuration_required')
        family = family or args.family
        with connect(connection) as conn:
            repo = MLRepository(conn)
            if (args.mode or cfg.get('dataset_mode','historical_contract')) == 'postgres_option_b':
                from sigard_ml.data_access.tabular_guard import forbid_tabular_reads
                from sigard_ml.forecasting.option_b_training import train as train_new
                with forbid_tabular_reads():
                    if args.action=='train':
                        if cfg.get('research_training_authorized') is not True:
                            raise DatasetBlocked('explicit_research_training_authorization_required')
                        result=train_new(conn,dataset_version=cfg['dataset_version'],family=family,
                            model_version=cfg['model_version'],horizon=cfg.get('horizon',1))
                    else:
                        frame=repo.research_frame(family,cfg['dataset_version'],horizon=cfg.get('horizon',1))
                        result=dict(status='inspected',rows=len(frame),data_source='postgresql',training_performed=False)
                write(output,result)
                print(json.dumps(dict(status=result['status'],data_source='postgresql',private_report_written=True)))
                return 0
            options = dict(horizon=cfg.get('horizon', 1),
                validation_start=date.fromisoformat(cfg['validation_start']) if cfg.get('validation_start') else None,
                test_start=date.fromisoformat(cfg['test_start']) if cfg.get('test_start') else None)
            if args.action == 'train':
                fitted = train(repo, family, cfg['dataset_version'],
                    training_authorized=cfg.get('research_training_authorized') is True, **options)
                # A backup of an explicit new research fit, never a registered
                # product or the input of an operational inference command.
                import joblib
                import io
                payload = io.BytesIO(); joblib.dump(fitted, payload, compress=3)
                backup = private_new(output.with_suffix('.joblib'))
                with backup.open('xb') as stream:
                    stream.write(payload.getvalue())
                result = fitted.report
            else:
                frame = dataset(repo, family, cfg['dataset_version'], **options)
                result = dict(rows=len(frame), data_source='postgresql', training_performed=False)
        write(output, dict(status='complete', family=family, **result))
        print(json.dumps(dict(status='complete', data_source='postgresql', private_report_written=True)))
        return 0
    except Exception as error:
        reason = str(error) if isinstance(error, DatasetBlocked) else 'inspect_private_contract'
        print(json.dumps(dict(status='blocked', reason=reason)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
