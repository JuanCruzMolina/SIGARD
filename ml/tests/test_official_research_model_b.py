"""Datos ficticios: autorización B, offsets exactos, NaN y ajuste sólo train."""

from copy import deepcopy
from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from sigard_ml.official.spatial_ml import research_model_b as b
from sigard_ml.official.spatial_ml.temporal_history import lookup


def permission():
    hashes = {name: "a" * 64 for name in ("scenario", "model_A", "history_5E")}
    auth = {"version": b.VERSION, "model": "B_presence_experimental", "research_training_authorized": True,
        "training_authorized": False, "scope": "isolated_retrospective_research_on_frozen_derivatives",
        "target_start": "2024-01-07", "target_end": "2024-06-08", "plan": b.PLAN,
        "negative_kind": "cero_asumido_experimental", "acknowledged_limits": b.ACKNOWLEDGED_LIMITS.copy(),
        "source_manifest_sha256": hashes, "features": b.FEATURES.copy(), "parameters": b.RF_PARAMETERS.copy(),
        "threshold": .5, "test_comparison": "exploratory_previously_examined",
        "decision_ref": "fictional-explicit-research-B", "responsible_ref": "fictional-researcher"}
    return {"version": b.VERSION, "output_dir": b.OUTPUT, "training_authorized": False, "research_authorization": auth}, hashes


def test_specific_permission_is_accepted():
    config, hashes = permission()
    b.validate_authorization(config, hashes)


@pytest.mark.parametrize("key,value", [
    ("model", "A"), ("research_training_authorized", False), ("training_authorized", True),
    ("scope", "operational"), ("target_start", "2023-01-01"), ("target_end", "2025-01-01"),
    ("negative_kind", "verified"), ("features", []), ("parameters", {}), ("threshold", .3),
    ("source_manifest_sha256", {}), ("test_comparison", "independent"), ("decision_ref", ""),
    ("acknowledged_limits", []), ("extra", True),
])
def test_no_silent_gate_bypass(key, value):
    config, hashes = permission()
    config["research_authorization"][key] = value
    with pytest.raises(ValueError):
        b.validate_authorization(config, hashes)


def test_official_gate_cannot_be_enabled():
    config, hashes = permission()
    config["training_authorized"] = True
    with pytest.raises(ValueError):
        b.validate_authorization(config, hashes)


@pytest.fixture
def data():
    keys = pd.DataFrame([{"radio_censal": radio, "fecha_inicio_semana": date(2024, 1, 7) + timedelta(weeks=week)}
        for radio in ("fiction_a", "fiction_b", "fiction_c") for week in range(12)])
    source = keys.copy()
    source["presencia_exp"] = pd.array([pd.NA if i % 11 == 0 else int(i % 3 == 0) for i in range(len(keys))], dtype="Int64")
    source["fuente_cero_asumido"] = source.presencia_exp.eq(0).fillna(False)
    source["fuente_desconocida"] = source.presencia_exp.isna()
    source["tipo_etiqueta"] = ["desconocida" if pd.isna(y) else "positivo_provisional" if y else "cero_asumido_experimental" for y in source.presencia_exp]
    source["casos_observados"] = pd.array([2 if not pd.isna(y) and y == 1 else pd.NA for y in source.presencia_exp], dtype="Int64")
    source["cobertura_comprobada"] = "unknown"
    source["disponibilidad_en_origen_acreditada"] = False
    reference = keys.copy()
    reference["apto_entrenamiento"] = False
    a_features = keys.assign(**{name: 2. for name in b.BASE})
    candidate = a_features.copy()
    series = pd.Series(source.presencia_exp.array, index=pd.MultiIndex.from_frame(keys))
    for lag, name in enumerate(b.LAGS, 1):
        candidate[name] = lookup(series, keys, lag)
    for name in b.LAGS:
        candidate[name + "_missing"] = candidate[name].isna()
    catalog = [{"feature": name, "source_week_offsets": [-lag], "maximum_source_week_offset": -lag,
                "uses_target_or_future_week": False} for lag, name in enumerate(b.LAGS, 1)]
    return candidate, reference, source, a_features, catalog


def test_all_history_cells_and_missing_flags_reconcile(data):
    original = deepcopy(data)
    result = b.validate_candidate(*data)
    assert result["rows"] == 36 and result["lag_cells_checked"] == 144
    assert result["missing_cells_retained"] > 0
    for before, after in zip(original[:4], data[:4]):
        pd.testing.assert_frame_equal(before, after)


@pytest.mark.parametrize("corruption", ["zero_fill", "flag", "target_offset", "future_offset", "base", "duplicate", "source_zero", "verified", "official"])
def test_corrupted_candidate_is_rejected(data, corruption):
    candidate, reference, source, a_features, catalog = deepcopy(data)
    if corruption == "zero_fill":
        candidate[b.LAGS[0]] = candidate[b.LAGS[0]].fillna(0)
    elif corruption == "flag":
        candidate.loc[0, b.MISSING[0]] = False
    elif corruption == "target_offset":
        catalog[0]["source_week_offsets"] = [0]
    elif corruption == "future_offset":
        catalog[0]["uses_target_or_future_week"] = True
    elif corruption == "base":
        candidate.loc[0, b.BASE[0]] += 1
    elif corruption == "duplicate":
        candidate = pd.concat([candidate, candidate.iloc[:1]], ignore_index=True)
    elif corruption == "source_zero":
        source["casos_observados"] = source.casos_observados.fillna(0)
    elif corruption == "verified":
        source["cobertura_comprobada"] = True
    else:
        reference.loc[0, "apto_entrenamiento"] = True
    with pytest.raises((ValueError, AssertionError)):
        b.validate_candidate(candidate, reference, source, a_features, catalog)


def test_matrix_preserves_na_and_rows(data):
    candidate = data[0]
    matrix = b.inference_matrix(candidate)
    assert matrix.shape == (36, 15)
    assert np.array_equal(matrix[b.LAGS].isna(), candidate[b.LAGS].isna())
    assert matrix[b.LAGS].isna().all(axis=1).any()


def training_frame(candidate):
    frame = candidate.copy()
    frame["partition"] = ["train"] * 24 + ["validation"] * 6 + ["test"] * 6
    frame["objetivo_semana_siguiente"] = pd.array([i % 2 for i in range(36)], dtype="Int64")
    frame.loc[3, "objetivo_semana_siguiente"] = pd.NA
    return frame


def test_fit_is_train_only_and_retains_incomplete_history(data):
    frame = training_frame(data[0])
    class SpyRF:
        def __init__(self, **params):
            assert params == b.RF_PARAMETERS
        def fit(self, x, y):
            self.x, self.y = x, y
    with patch.object(b, "RandomForestClassifier", SpyRF):
        estimator, train, _ = b.fit_model_b(frame)
    assert len(train) == 23 and len(estimator.x) == 23
    assert set(train.partition) == {"train"}
    assert estimator.x[b.LAGS].isna().all(axis=1).any()
    assert len(estimator.y) == 23


def test_incompatible_nan_environment_stops_before_fit(data):
    with patch.object(b, "installed_capabilities", return_value={"native_nan_supported": False}), patch.object(b, "RandomForestClassifier") as estimator:
        with pytest.raises(ValueError, match="incompatible"):
            b.fit_model_b(training_frame(data[0]))
        estimator.assert_not_called()


def test_group_permutation_preserves_masks_weeks_and_context(data):
    matrix = b.inference_matrix(data[0])
    first, eligible, changed = b.permute_observed_history(matrix, data[0].fecha_inicio_semana, 20261016)
    second, _, _ = b.permute_observed_history(matrix, data[0].fecha_inicio_semana, 20261016)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(first[b.BASE + b.MISSING], matrix[b.BASE + b.MISSING])
    assert np.array_equal(first[b.LAGS].isna(), matrix[b.LAGS].isna())
    assert eligible >= changed
    for week, indices in data[0].groupby("fecha_inicio_semana").groups.items():
        for name in b.LAGS:
            assert sorted(first.loc[indices, name].dropna()) == sorted(matrix.loc[indices, name].dropna())


def test_numeric_metrics_retain_undefined_precision_and_audit_identities():
    y, p = np.array([0, 1, 1, 0]), np.array([.1, .4, .3, .2])
    result, audit = b.numeric_metrics(y, p), []
    b.audit_sklearn(y, p, result, audit, "fictional")
    assert result["precision"] is None and result["recall"] == 0
    assert result["tn"] == 2 and result["fn"] == 2
    assert all(row["matches"] for row in audit)
