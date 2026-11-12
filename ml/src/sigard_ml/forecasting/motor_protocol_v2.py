"""Prespecified corrective v2 protocol. No data access, fitting or selection here.

Reuses the v1 cuts, blocks, 28-day purge, years and bootstrap. v1 stays frozen.
"""
from sigard_ml.forecasting.motor_protocol import (PROTOCOL as V1, VERSION as V1_VERSION,
    STATIC, HISTORY, CLIMATE, COUNT_BASELINES)
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS

VERSION = 'sigard-two-capabilities-h1-corrective-20261112-v1'
SEED = 20261112

CITY = ('city_count_origin', 'city_mean_2', 'city_mean_4', 'city_trend_1',
        'city_positive_radios_origin', 'city_log_growth')
PROPENSITY = ('radio_hist_positive_rate', 'radio_hist_count_rate',
              'radio_hist_season_positive_rate', 'weeks_since_last_positive')

PRINCIPAL = 'rf_v2_city_propensity'
SECONDARY = 'logit_v2_factors'
COUNT = 'residual_v2'
PRESENCE = (PRINCIPAL, SECONDARY)
FEATURES = {
    PRINCIPAL: STATIC + HISTORY + CLIMATE + CITY + PROPENSITY,
    SECONDARY: CITY + PROPENSITY,
    COUNT: STATIC + HISTORY + CLIMATE + CITY + PROPENSITY,
}
RF_V2_PARAMETERS = {**RF_PARAMETERS, 'class_weight': None, 'max_features': .5, 'random_state': SEED}
LOGIT_PARAMETERS = dict(C=1., max_iter=1000)
RESIDUAL_V2_PARAMETERS = dict(V1['residual_parameters'])

PRESENCE_REFERENCES = ('presence_latest_count', 'presence_latest', 'presence_territorial',
                       'presence_seasonal', 'random')
TOPK = dict(k=10, sensitivity=[5, 25], tie_seed=SEED,
            selection='exactly min(k, radios) per target week; descending score',
            tie_break='seeded permutation per target week: numpy default_rng([tie_seed, target_week.toordinal()]) '
                      'over radios ordered by radio_id; deterministic and independent of row order')

SUCCESS_CRITERIA = {
    'P1': 'recall@10 desarrollo 2021–2023 de rf_v2 > presence_latest_count con IC95 bootstrap pareado '
          '(bloques de 4 semanas, 1000 réplicas) con límite inferior > 0.',
    'P2': 'en ningún año de desarrollo, recall@10 de rf_v2 menor que latest_count en más de 0,03.',
    'P3': 'onset_recall@10 de rf_v2 > presence_territorial (informar IC).',
    'Q1': 'MAE de residual_v2 < count_latest en desarrollo con IC95 superior < 0',
    'Q2': 'sesgo y MAE en conteos altos no peores que 5 %.',
    '2024': '2024 se informa aparte como comparación ya observada; no decide nada.',
    'logit': 'logit_v2 es interpretativo y no puede reemplazar al principal si P1–P3 fallan.',
}
CRITERIA_OPERATIONALIZATION = {
    'recall_at_k': 'sum over development weeks of positives (target_count>0) inside the exact top-k / sum of positives',
    'onset': 'target_count>0 with known count_origin == 0 (same as v1 top_zones); not a first clinical episode',
    'P1': 'paired difference rf_v2 - presence_latest_count of recall@10 over 2021-2023; v1 paired_interval '
          'moving-block bootstrap (4 weeks within epi year, 1000 resamples, seed 20261102) of '
          'sum(hits_m - hits_ref)/sum(positives); pass iff lower95 > 0',
    'P2': 'for each year in 2021, 2022, 2023: recall@10(rf_v2) >= recall@10(presence_latest_count) - 0.03',
    'P3': 'point estimate onset_recall@10(rf_v2) > onset_recall@10(presence_territorial); paired interval reported',
    'Q1': 'v1 paired_interval with loss=mae, residual_v2 vs count_latest, development only; pass iff '
          'mean MAE lower and upper95 < 0',
    'Q2': 'bias: |mean_bias(residual_v2)| <= |mean_bias(count_latest)| + 0.05 * mean(target) (v1 bias rule); '
          'high counts: MAE(residual_v2 | target >= tail_limit) <= 1.05 * MAE(count_latest | same rows), '
          'tail_limit = max(2, training target 90th percentile) fixed per fold as in v1',
    'presence_success': 'P1 and P2 and P3', 'count_success': 'Q1 and Q2',
}

PROTOCOL = dict(
    version=VERSION, base_protocol=V1_VERSION, horizon_weeks=1, seed=SEED,
    source=V1['source'], coverage_years=V1['coverage_years'],
    development_target_years=V1['development_target_years'],
    comparison_target_years=V1['comparison_target_years'], warmup_target_years=V1['warmup_target_years'],
    walk_forward=V1['walk_forward'], purge_weeks=V1['purge_weeks'], purge_rule=V1['purge_rule'],
    minimum_training_weeks=V1['minimum_training_weeks'], bootstrap=dict(V1['bootstrap']),
    blocks='16 = 4 per target year 2021-2024 (12 development + 4 comparison 2024)',
    features={k: list(v) for k, v in FEATURES.items()},
    new_features=dict(
        city=list(CITY), propensity=list(PROPENSITY),
        city_rule='sums over the common-mask radios of the origin week and earlier weeks only; NaN when any '
                  'radio count of a needed week is unknown; city_mean_k needs all k weeks; '
                  'city_log_growth = log1p(origin) - log1p(lag_1)',
        propensity_rule='per radio, expanding from 2020, only mature labels: rows whose target_end < '
                        'origin - 28 days (same as the purge) with known target_count; NaN without support',
        season_rule='mature labels from earlier target epi years whose epi week number is within +-4 of the '
                    'row target week number, circular distance with 53 weeks (as v1 seasonal baseline)',
        weeks_since_last_positive='(origin_week - last mature positive target_week) / 7; NaN if none'),
    candidates=dict(
        principal=dict(name=PRINCIPAL, estimator='sklearn RandomForestClassifier',
                       parameters=dict(RF_V2_PARAMETERS),
                       note='RF_PARAMETERS v1 except class_weight=None and max_features=0.5; seed 20261112'),
        secondary=dict(name=SECONDARY, estimator='median imputation + missing indicators -> StandardScaler -> '
                       'LogisticRegression', parameters=dict(LOGIT_PARAMETERS),
                       note='imputer and scaler fitted on the training fold only; max_iter only for convergence'),
        count=dict(name=COUNT, estimator='v3._regressor HistGradientBoostingRegressor on persistence residual',
                   parameters=dict(RESIDUAL_V2_PARAMETERS), loss='absolute_error',
                   seed=V1['residual_seed'], shrinkage=V1['residual_shrinkage'],
                   output='max(0, count_latest + 0.5 * residual)')),
    decision=dict(rule='top_k', **TOPK, calibration=None, thresholds=None,
                  note='no calibration and no thresholds in this campaign'),
    presence_references=list(PRESENCE_REFERENCES),
    presence_latest_count='order by count_origin descending; unknown origin uses presence_territorial as '
                          'primary value (as Fase 0); ties broken by presence_territorial (v1 baseline '
                          'fitted per fold); remaining exact ties by the top-k tie rule',
    random_reference=dict(permutations=100, seed=SEED, metric='average over permutations'),
    count_references=list(COUNT_BASELINES),
    success_criteria=SUCCESS_CRITERIA, criteria_operationalization=CRITERIA_OPERATIONALIZATION,
    comparison_status=V1['comparison_status'],
    prohibited=['hyperparameter_search', 'change_k_or_criteria_after_results', 'add_candidates',
                'calibration', 'thresholds', 'random_row_split', 'new_source', 'operational_activation',
                'frontend_change', 'modify_v1_protocol_or_results', 'select_with_2024'],
    expected_fits=dict(blocks=16, models_per_block=3, total=48, final_refit=False),
    operational_enabled=False, scientifically_validated=False,
)
