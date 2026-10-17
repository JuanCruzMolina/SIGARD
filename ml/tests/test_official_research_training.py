"""Ficticios: autorización diferenciada, fuga, particiones y reproducibilidad."""

from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from sigard_ml.official.spatial_ml import research_training as research
from sigard_ml.official.spatial_ml.assumed_scenario import ZERO_KIND, chronological_review
from sigard_ml.official.spatial_ml.experiment_selection import BASE
from sigard_ml.official.spatial_ml.features import KEYS, calendar_predictors
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR


def permission(**changes):
    return {"version": research.VERSION, "decision_ref": "fictional-explicit-user-authorization",
        "responsible_ref": "fictional-research-custodian", "research_training_authorized": True,
        "training_authorized": False, "scope": "isolated_retrospective_research_on_frozen_derivatives",
        "scenario_manifest_sha256": "a" * 64, "target_start": "2024-01-07", "target_end": "2024-06-08",
        "plan": research.PLAN, "model": "A", "negative_kind": ZERO_KIND,
        "acknowledged_limits": research.ACKNOWLEDGED_LIMITS.copy(), **changes}


@pytest.mark.parametrize("changes", [
    {"research_training_authorized": False}, {"training_authorized": True},
    {"scenario_manifest_sha256": "b" * 64}, {"target_start": "2024-01-01"},
    {"target_end": "2024-12-31"}, {"model": "B"}, {"plan": "other"},
    {"negative_kind": "verified"}, {"scope": "production"}, {"acknowledged_limits": []},
    {"decision_ref": ""}, {"responsible_ref": ""}, {"extra": True},
])
def test_rejects_missing_or_broadened_research_permission(changes):
    with pytest.raises(ValueError):
        research.validate_research_authorization(permission(**changes), "a" * 64)


def test_permission_is_distinct_and_does_not_mutate_official_flags():
    value = permission()
    before = deepcopy(value)
    research.validate_research_authorization(value, "a" * 64)
    assert value == before and value["training_authorized"] is False
    with pytest.raises(ValueError):
        research.validate_research_authorization(None, "a" * 64)


@pytest.fixture
def design():
    # Include the full range required by inherited diagnostic split plans.
    rows = []
    for radio in range(263):
        for week in range(108):
            origin = date(2022, 12, 18) + timedelta(weeks=week)
            target = origin + timedelta(days=7)
            unknown = radio == 262
            positive = radio % 3 == week % 3
            y = None if unknown else int(positive)
            rows.append({"radio_censal": f"fictional_{radio:03d}", "fecha_inicio_semana": origin,
                "fecha_inicio_semana_objetivo": target, "fecha_fin_semana_objetivo": target + timedelta(days=6),
                "objetivo_semana_siguiente": y, "objetivo_original": 1 if positive and not unknown else None,
                "tipo_etiqueta": "desconocida" if unknown else "positivo_provisional" if positive else ZERO_KIND,
                "apto_entrenamiento": False, "panel_fechas": "expanded", "pendientes_semana_objetivo": 0,
                "semana_objetivo_parcial": False,
                "en_intervalo_autorizado": date(2024, 1, 7) <= target <= date(2024, 6, 2)})
    labels = pd.DataFrame(rows).sort_values(KEYS).reset_index(drop=True)
    labels["objetivo_semana_siguiente"] = labels.objetivo_semana_siguiente.astype("Int8")
    # Unknown out-of-interval cells are retained; no extra assumed negatives.
    outside = ~labels.en_intervalo_autorizado & labels.objetivo_semana_siguiente.eq(0)
    labels.loc[outside, "objetivo_semana_siguiente"] = pd.NA
    labels.loc[outside, "tipo_etiqueta"] = "desconocida"
    calendar = labels[KEYS].copy()
    yw = calendar.fecha_inicio_semana.map(DEFAULT_CALENDAR.date_week)
    calendar["anio_epidemiologico"] = yw.map(lambda x: x[0])
    calendar["semana_epidemiologica"] = yw.map(lambda x: x[1])
    features = calendar_predictors(calendar)
    for i, name in enumerate(BASE[:4]):
        features[name] = labels.radio_censal.map(lambda name: int(name[-3:]) + i + 1)
    features = features[KEYS + BASE]
    splits, _ = chronological_review(labels)
    policies = [{"feature": name, "uses_future_week": False,
                 "depends_on_unknown_origin_or_past_counts": False, "source_week_offsets": None} for name in BASE]
    return labels, features, splits, policies


def test_unknown_exclusion_and_exact_purged_target_periods(design):
    frame, summary = research.validate_design(*design)
    for part, weeks in (("train", 8), ("validation", 8), ("test", 4)):
        assert summary[part]["used"] == 262 * weeks
        assert summary[part]["unknown_excluded"] == weeks
        assert summary[part]["target_weeks"] == weeks
    purged = frame[frame.en_intervalo_autorizado & ~frame.partition.isin(research.PERIODS)]
    assert set(purged.fecha_inicio_semana_objetivo) == {date(2024, 3, 3), date(2024, 5, 5)}
    assert not frame.apto_entrenamiento.any()


@pytest.mark.parametrize("corruption", ["future_calendar", "label_as_feature", "future_policy", "blocked_zero",
    "different_split", "missing_predictor", "nonfinite", "duplicate_key", "variable_static", "next_week_gap"])
def test_fundamental_integrity_corruption_blocks_experiment(design, corruption):
    labels, features, splits, policies = deepcopy(design)
    if corruption == "future_calendar":
        features.loc[0, "semana_epidemiologica"] += 1
    elif corruption == "label_as_feature":
        features["target"] = labels.objetivo_semana_siguiente
    elif corruption == "future_policy":
        policies[0]["source_week_offsets"] = [1]
    elif corruption == "blocked_zero":
        row = labels.index[labels.objetivo_semana_siguiente.eq(0)][0]
        labels.loc[row, "pendientes_semana_objetivo"] = 1
    elif corruption == "different_split":
        splits.loc[splits.plan.eq(research.PLAN) & splits.partition.eq("test"), "partition"] = "train"
    elif corruption == "missing_predictor":
        features.loc[0, "poblacion"] = np.nan
    elif corruption == "nonfinite":
        features["poblacion"] = features.poblacion.astype(float)
        features.loc[0, "poblacion"] = np.inf
    elif corruption == "duplicate_key":
        features = pd.concat([features, features.iloc[:1]], ignore_index=True)
    elif corruption == "variable_static":
        features.loc[0, "poblacion"] += 1
    elif corruption == "next_week_gap":
        labels.loc[0, "fecha_inicio_semana_objetivo"] += timedelta(days=7)
    with pytest.raises((ValueError, AssertionError)):
        research.validate_design(labels, features, splits, policies)


def test_metrics_baseline_ap_calibration_and_single_class():
    y = [0, 0, 0, 1]
    p = np.repeat(0.25, 4)
    result = research.classification_metrics(y, p)
    assert result["average_precision_pr_auc"] == 0.25
    assert result["roc_auc"] == 0.5
    assert result["brier"] == 0.1875
    assert result["confusion_matrix_true_rows_predicted_columns_0_1"] == [[3, 0], [1, 0]]
    assert result["precision"] == result["recall"] == result["f1"] == 0
    bins = research.reliability_bins(y, p)
    assert len(bins) == 1 and bins[0]["n"] == 4 and bins[0]["fraction_positive"] == 0.25
    single = research.classification_metrics([0, 0], [0.2, 0.4])
    assert single["roc_auc"] is single["average_precision_pr_auc"] is None
    edge_bins = research.reliability_bins([0, 1], [0, 1])
    assert [r["bin"] for r in edge_bins] == [0, 9]


def test_evaluation_changes_cannot_affect_fit_prior_or_threshold(design):
    frame, _ = research.validate_design(*design)
    # Small fictitious training matrix; retain actual predeclared RF parameters.
    frame = frame[frame.radio_censal.isin([f"fictional_{i:03d}" for i in [*range(18), 262]])].copy()
    original = frame.copy(deep=True)
    models = research.fit_models(frame)
    future = ~frame.partition.eq("train")
    frame.loc[future, "objetivo_semana_siguiente"] = 1 - frame.loc[future, "objetivo_semana_siguiente"]
    frame.loc[future, "poblacion"] = 99999
    repeated = research.fit_models(frame)
    for name in models:
        assert np.array_equal(models[name].predict_proba(original[BASE]), repeated[name].predict_proba(original[BASE]))
    known_train = original[original.partition.eq("train") & original.objetivo_semana_siguiente.notna()]
    assert models["training_prevalence"].class_prior_[1] == float(known_train.objetivo_semana_siguiente.mean())
    assert research.THRESHOLD == 0.5
    assert models["random_forest_A"].get_params()["n_estimators"] == 400
    predictions, metrics, calibration, temporal = research.evaluate_models(original, models)
    assert predictions.objetivo_semana_siguiente.isna().sum() == 20
    assert predictions["random_forest_A_probability"].notna().all()
    assert metrics["random_forest_A"]["test"]["n"] == 18 * 4
    assert not calibration.empty and len(temporal) == 40


def test_tampered_frozen_artifact_is_rejected(tmp_path):
    path = tmp_path / "private.txt"
    path.write_text("fictional", encoding="utf-8")
    hashes = {str(path): research.digest_path(path)}
    research.verify_frozen_hashes(hashes)
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError):
        research.verify_frozen_hashes(hashes)


def test_parquet_string_null_normalization_preserves_strict_value_check():
    rebuilt = pd.DataFrame({"metadata_ref": pd.Series([None, "fictional"], dtype=object),
                            "target": pd.Series([pd.NA, 0], dtype="Int8")})
    stored = pd.read_parquet(BytesIO(rebuilt.to_parquet(index=False)))
    research.assert_parquet_equivalent(stored, rebuilt)
    changed = rebuilt.copy(deep=True)
    changed.loc[1, "target"] = 1
    with pytest.raises(AssertionError):
        research.assert_parquet_equivalent(stored, changed)


def test_missing_authorization_blocks_before_fit_or_output(tmp_path, monkeypatch):
    root = tmp_path
    inputs = {"access_config": root / research.DEFAULTS["access_config"],
              "phase5a_dir": root / research.DEFAULTS["phase5a_dir"],
              "phase5b_dir": root / research.DEFAULTS["phase5b_dir"],
              "scenario_dir": root / research.DEFAULTS["scenario_dir"]}
    inputs["scenario_dir"].mkdir(parents=True)
    (inputs["scenario_dir"] / "integrity_manifest.private.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(research, "require_branch", lambda root: None)
    monkeypatch.setattr(research.subprocess, "run", lambda *a, **k: type("Result", (), {"returncode": 0})())
    def forbidden(*args, **kwargs):
        raise AssertionError("fit cannot run without authorization")
    monkeypatch.setattr(research.RandomForestClassifier, "fit", forbidden)
    with pytest.raises(ValueError):
        research.run_research(root, deepcopy(research.DEFAULTS))
    assert not (root / research.DEFAULTS["output_dir"]).exists()


@pytest.mark.parametrize("destination", ["frontend/public/result", "backend/result", "data/processed/official", "data/interim/official/result"])
def test_rejects_nonisolated_output_paths(tmp_path, destination):
    options = {**research.DEFAULTS, "output_dir": destination}
    with pytest.raises(ValueError):
        research.private_paths(tmp_path, options)
