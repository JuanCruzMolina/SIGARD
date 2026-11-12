"""Prespecified stage-2 protocol. No data access, fitting or selection here."""
from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS
from sigard_ml.forecasting.v3 import PROTOCOL as V3_PROTOCOL

VERSION = 'sigard-two-capabilities-h1-research-20261102-v1'
SEED = 20261102
STATIC = ('superficie_km2','poblacion','densidad_poblacional','cantidad_vecinos',
          'semana_epidemiologica','estacionalidad_seno','estacionalidad_coseno')
HISTORY = ('count_origin','presence_origin',*[f'count_lag_{i}' for i in range(1,5)],
    *[f'presence_lag_{i}' for i in range(1,5)],'mean_2','mean_4','trend_1',
    'known_2','known_4','neighbor_count_mean','neighbor_presence_mean','neighbor_known_fraction')
CLIMATE = ('temperature','humidity','precipitation','temperature_lag_1','humidity_lag_1',
    'precipitation_lag_1','temperature_mean_4','precipitation_sum_4',
    'temperature_history','humidity_history','precipitation_history','temperature_anomaly')
PRESENCE = ('rf_A_reference','rf_A_epi_climate','rf_A_epi_no_climate')
FEATURES = {PRESENCE[0]:STATIC,PRESENCE[1]:STATIC+HISTORY+CLIMATE,
            PRESENCE[2]:STATIC+HISTORY,'residual_h1':STATIC+HISTORY+CLIMATE}
PRESENCE_BASELINES = ('presence_latest','presence_prior','presence_territorial','presence_seasonal')
COUNT_BASELINES = ('count_latest','count_historical_lag1','count_training_mean')
PROTOCOL = dict(version=VERSION,horizon_weeks=1,active_ml_families=['RandomForest_presence','persistence_residual_counts'],
    presence_candidates=list(PRESENCE),count_candidates=['residual_h1'],
    features={k:list(v) for k,v in FEATURES.items()},rf_parameters=dict(RF_PARAMETERS),
    residual_parameters=dict(V3_PROTOCOL['residual_parameters']),residual_seed=20261021,residual_shrinkage=.5,
    source='only consolidated PostgreSQL stage1 dataset; previous labels are not interchangeable',
    coverage_years=list(range(2020,2025)),development_target_years=[2021,2022,2023],
    comparison_target_years=[2024],warmup_target_years=[2020],
    walk_forward='four consecutive 13-week target blocks per epi year; all radios stay together; expanding history',
    purge_weeks=4,purge_rule='train target_end < first evaluation origin - 28 days; max explicit lag is four weeks',
    minimum_training_weeks=26,
    calibration=dict(inner_weeks=26,calibration_weeks=13,threshold_weeks=13,
        base_min_weeks=26,base_min_positive=30,calibration_min_positive=50,
        calibration_min_positive_weeks=8,calibration_min_negative=100,
        threshold_min_positive=20,threshold_min_positive_weeks=4,
        method='sigmoid C=1 on first 13 inner weeks only if support holds; base is not refit after calibration',
        inner_purge='same four-week purge also separates calibration outcomes from threshold origins',
        otherwise='raw score; original 0.5 fixed threshold when inner threshold support is insufficient',
        support_is_computational_not_power=True),
    thresholds=[.05,.1,.15,.2,.3,.4,.5,.6,.7,.8,.9],
    threshold_rule='max inner F1 subject to FPR<=0.20; ties precision then higher threshold; no outer labels',
    baseline_territorial_prior_weight=10.,baseline_seasonal_window_weeks=2,
    presence_selection=dict(brier_relative_improvement=.03,year_max_brier_ratio=1.10,
        year_absolute_tolerance=.0001,minimum_year_wins=2,
        average_precision_max_loss=.01,f1_max_loss=.03,
        paired_weekly_upper95_below_zero=True,
        enhanced='must beat re-trained A and every simple presence reference',
        reference_A='may be retained only if it passes the same gates against every simple reference',
        fallback='lowest development Brier simple baseline; never choose using 2024',
        tie='prefer no-climate among approved enhanced candidates if Brier is equal'),
    count_selection=dict(mae_relative_improvement=.03,rmse_max_ratio=1.02,
        bias_mean_y_tolerance=.05,high_count_mae_max_ratio=1.05,high_week_rmse_max_ratio=1.05,
        zero_mae_max_ratio=1.10,zero_mae_absolute_tolerance=.005,positive_mae_max_ratio=1.02,
        year_max_mae_ratio=1.10,minimum_year_wins=2,paired_weekly_upper95_below_zero=True,
        references=list(COUNT_BASELINES),fallback='count_latest, explicitly a statistical persistence baseline'),
    high_count='max(2, training target 90th percentile), fixed separately for each fold',
    high_week='max(1, training weekly total 80th percentile), fixed separately for each fold',
    bootstrap=dict(block_weeks=4,resamples=1000,seed=SEED,
        unit='whole chronological weeks with all radios paired; contiguous blocks do not cross epi-year boundaries',
        meaning='descriptive internal uncertainty, not external confirmation or independent cells'),
    top_zones=dict(k=10,ties='fractional inclusion at the tied cutoff',
        onset='positive target and zero known origin, not a first infection or first clinical episode'),
    census='population/density use stage1 asof-gated values, never substitute the future 2022 descriptive population',
    static_geography='fixed versioned study units; historical geometry/graph availability unaccredited',
    temporal_availability='measurements through closed origin only; arrival unknown => retrospective reconstruction',
    final_refit='after development decision and 2024 evaluation; selected ML only on mature 2020-2024 labels; '
        'baselines retain sufficient training statistics without claiming an ML fit; no operational predictions',
    archived=['original_A','historical_B','historical_V3_h1_h2_h4','old_Poisson_core','old_metrics_and_baselines'],
    prohibited=['train_historical_B','direct_Poisson','hurdle','probability_times_unconditional_count',
        'random_row_split','parameter_search','new_source','operational_activation','frontend_change'],
    operational_enabled=False,scientifically_validated=False,
    comparison_status='2024 previously observed; retrospective evaluation, never independent external test')
