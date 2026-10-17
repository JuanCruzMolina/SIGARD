"""Fase 5E: fixtures sin fit, sin datos de pacientes ni modelos nuevos."""

import ast
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sigard_ml.official.spatial_ml import temporal_history as h
from sigard_ml.official.spatial_ml import temporal_feasibility as phase
from sigard_ml.official.spatial_ml.temporal_model_a_audit import manual_tree_leaves


def fixture_data():
    weekly, labels, context = [], [], []
    for radio in ("fiction_a", "fiction_b", "fiction_c"):
        for week in range(22):
            day = h.START + timedelta(weeks=week)
            unknown = radio == "fiction_c" or (radio == "fiction_b" and week == 2)
            positive = not unknown and (radio == "fiction_b" or week % 2 == 0)
            count = 2 if positive else None
            pending = 1 if unknown or (radio == "fiction_b" and week < 5) else 0
            weekly.append({"radio_censal": radio, "fecha_inicio_semana": day,
                "fecha_fin_semana": day + timedelta(days=6), "casos_observados": count,
                "registros_pendientes_posibles": pending, "ventana_semanal_parcial": False,
                "en_intervalo_autorizado": True, "ausencia_asumida_autorizada": not unknown and not positive})
            labels.append({"radio_censal": radio, "fecha_inicio_semana": day - timedelta(weeks=1),
                "fecha_inicio_semana_objetivo": day, "objetivo_semana_siguiente": None if unknown else int(positive),
                "tipo_etiqueta": "desconocida" if unknown else "positivo_provisional" if positive else "cero_asumido_experimental",
                "en_intervalo_autorizado": True, "partition": "train" if week < 8 else "validation" if week < 17 else "test"})
            context.append({"radio_censal": radio, "fecha_inicio_semana": day, "estado_cobertura": "desconocida",
                "estado_observacion": "provisional", "cobertura_comprobada": False,
                "registros_fecha_aproximada": 0, "registros_asignacion_incierta": 0,
                "version_fecha": "fictional", "version_transformacion": "fictional"})
    weekly, labels, context = pd.DataFrame(weekly), pd.DataFrame(labels), pd.DataFrame(context)
    weekly["casos_observados"] = weekly.casos_observados.astype("Int64")
    labels["objetivo_semana_siguiente"] = labels.objetivo_semana_siguiente.astype("Int8")
    return weekly, labels, context


@pytest.fixture
def prepared():
    weekly, labels, context = fixture_data()
    source = h.source_history(weekly, labels, context)
    neighbors = {"fiction_a": ["fiction_b"], "fiction_b": ["fiction_a", "fiction_c"], "fiction_c": ["fiction_b"]}
    matrix, operational, catalog = h.history_matrix(source, labels[h.KEYS], neighbors)
    return source, labels, neighbors, matrix, operational, catalog


def test_explicit_presence_zero_does_not_replace_unknown_count():
    weekly, labels, context = fixture_data()
    before = weekly.copy(deep=True)
    source = h.source_history(weekly, labels, context)
    pd.testing.assert_frame_equal(weekly, before)
    zero = source.presencia_exp.eq(0)
    assert zero.any() and source.loc[zero, "registros_provisionales"].isna().all()
    assert source.loc[source.presencia_exp.isna(), "registros_provisionales"].isna().all()
    assert source.registros_provisionales.notna().sum() == weekly.casos_observados.notna().sum()
    assert not source.disponibilidad_en_origen_acreditada.any()


def test_source_week_uses_label_target_date_not_label_origin():
    source = h.source_history(*fixture_data())
    row = source[source.radio_censal.eq("fiction_a") & source.fecha_inicio_semana.eq(h.START)].iloc[0]
    assert row.presencia_exp == 1 and row.registros_provisionales == 2
    row = source[source.radio_censal.eq("fiction_a") & source.fecha_inicio_semana.eq(h.START + timedelta(weeks=1))].iloc[0]
    assert row.presencia_exp == 0 and pd.isna(row.registros_provisionales)


@pytest.mark.parametrize("corruption", ["zero_with_pending", "zero_not_authorized", "zero_has_count", "positive_without_count", "wrong_kind", "duplicate"])
def test_inconsistent_weekly_provenance_rejected(corruption):
    weekly, labels, context = fixture_data()
    zero = weekly.index[weekly.ausencia_asumida_autorizada][0]
    positive = weekly.index[weekly.casos_observados.notna()][0]
    if corruption == "zero_with_pending":
        weekly.loc[zero, "registros_pendientes_posibles"] = 1
    elif corruption == "zero_not_authorized":
        weekly.loc[zero, "ausencia_asumida_autorizada"] = False
    elif corruption == "zero_has_count":
        weekly.loc[zero, "casos_observados"] = 0
    elif corruption == "positive_without_count":
        weekly.loc[positive, "casos_observados"] = pd.NA
    elif corruption == "wrong_kind":
        labels.loc[zero, "tipo_etiqueta"] = "verified_zero"
    else:
        weekly = pd.concat([weekly, weekly.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError):
        h.source_history(weekly, labels, context)


def test_lag_one_and_window_four_are_strictly_before_origin(prepared):
    source, labels, neighbors, matrix, operational, catalog = prepared
    origin = h.START + timedelta(weeks=4)
    row = matrix[matrix.radio_censal.eq("fiction_a") & matrix.fecha_inicio_semana.eq(origin)].iloc[0]
    assert [row[f"local_presencia_exp_rezago_{lag}"] for lag in (1, 2, 3, 4)] == [0, 1, 0, 1]
    assert row.local_presencia_exp_acumulado_4 == 2
    assert pd.isna(row.local_registros_provisionales_acumulado_4)
    assert row.local_fuente_cero_asumido_celdas_4 == 2
    assert all(row["maximum_source_week_offset"] == -1 or len(row["source_week_offsets"]) == 1 for row in catalog)
    assert all(max(row["source_week_offsets"]) < 0 for row in catalog)
    early = matrix[matrix.fecha_inicio_semana.lt(h.START + timedelta(weeks=8))]
    assert early.local_presencia_exp_acumulado_8.isna().all()
    assert len(matrix) == len(labels)


def test_missing_week_never_skipped_or_summed_as_zero(prepared):
    source, labels, neighbors, *_ = prepared
    missing_day = h.START + timedelta(weeks=3)
    source = source[~(source.radio_censal.eq("fiction_a") & source.fecha_inicio_semana.eq(missing_day))]
    matrix, *_ = h.history_matrix(source, labels[h.KEYS], neighbors)
    row = matrix[matrix.radio_censal.eq("fiction_a") & matrix.fecha_inicio_semana.eq(missing_day + timedelta(weeks=1))].iloc[0]
    assert pd.isna(row.local_presencia_exp_rezago_1)
    assert row.local_presencia_exp_rezago_2 == 1
    assert pd.isna(row.local_presencia_exp_acumulado_4)


def test_neighbors_require_all_neighbors_all_weeks(prepared):
    source, labels, neighbors, matrix, *_ = prepared
    origin = h.START + timedelta(weeks=5)
    a = matrix[matrix.radio_censal.eq("fiction_a") & matrix.fecha_inicio_semana.eq(origin)].iloc[0]
    b = matrix[matrix.radio_censal.eq("fiction_b") & matrix.fecha_inicio_semana.eq(origin)].iloc[0]
    assert a.vecinos_presencia_exp_rezago_1 == 1
    assert pd.isna(b.vecinos_presencia_exp_rezago_1)
    assert pd.isna(a.vecinos_presencia_exp_acumulado_4)
    empty = {name: [] for name in neighbors}
    no_neighbors, *_ = h.history_matrix(source, labels[h.KEYS], empty)
    assert no_neighbors.vecinos_presencia_exp_rezago_1.isna().all()


def test_pending_positives_preserve_presence_but_mask_strict_counts(prepared):
    source, *_ = prepared
    pending = source[source.fuente_pendientes & source.presencia_exp.eq(1)]
    assert not pending.empty and pending.registros_provisionales.notna().all()
    assert pending.registros_sin_pendientes.isna().all()
    assert source[source.fuente_pendientes & source.presencia_exp.isna()].fuente_cero_asumido.eq(False).all()


def test_operational_unknown_is_not_unavailable_false_observation(prepared):
    *_, operational, catalog = prepared
    values = [r["feature"] for r in catalog]
    assert operational[values].isna().all().all()
    assert not operational[[name + "_valor_disponible" for name in values]].any().any()


def test_future_and_origin_values_cannot_affect_past_history(prepared):
    source, labels, neighbors, matrix, *_ = prepared
    origin = h.START + timedelta(weeks=10)
    altered = source.copy(deep=True)
    future = altered.fecha_inicio_semana.ge(origin)
    for name in h.TRACKS:
        altered.loc[future, name] = 0 if name == "presencia_exp" else 999
    for name in ("fuente_cero_asumido", "fuente_pendientes", "fuente_fecha_aproximada", "fuente_desconocida"):
        altered.loc[future, name] = ~altered.loc[future, name]
    changed, *_ = h.history_matrix(altered, labels[h.KEYS], neighbors)
    pd.testing.assert_frame_equal(matrix[matrix.fecha_inicio_semana.le(origin)], changed[changed.fecha_inicio_semana.le(origin)])


def test_input_order_does_not_change_results(prepared):
    source, labels, neighbors, matrix, *_ = prepared
    repeated, *_ = h.history_matrix(source.iloc[::-1], labels[h.KEYS].iloc[::-1], neighbors)
    pd.testing.assert_frame_equal(matrix, repeated)


def test_availability_reports_classes_and_retains_missing_rows(prepared):
    source, labels, neighbors, matrix, operational, catalog = prepared
    availability, by_week = h.availability_report(matrix, labels, catalog)
    support = phase.training_support(availability)
    assert len(availability) == 3 * (36 + 6)
    assert not by_week.empty and len(support) == 42
    for row in availability.to_dict("records"):
        assert row["rows_feature_known"] + row["rows_retained_with_missing_features"] == row["grid_rows"]
        assert row["target_positive_when_feature_known"] + row["target_negative_when_feature_known"] == row["rows_feature_and_target_known"]
        assert row["operational_rows_available"] == 0
    pending, states = h.pending_report(source, matrix, labels)
    assert len(pending) == 6 and states.cells.sum() == len(source)


@pytest.mark.parametrize("neighbors", [
    {"a": ["a"]}, {"a": ["b"], "b": []}, {"a": ["b", "b"], "b": ["a"]},
])
def test_invalid_graph_is_rejected(neighbors):
    with pytest.raises(ValueError):
        h.validate_neighbors(neighbors, neighbors)


@pytest.mark.parametrize("lag", [0, -1, 1.5])
def test_nonpast_or_fractional_lags_rejected(lag):
    keys = pd.DataFrame({"radio_censal": ["a"], "fecha_inicio_semana": [h.START]})
    with pytest.raises(ValueError):
        h.lookup(pd.Series(dtype="Int64"), keys, lag)


def test_float32_manual_tree_traversal_uses_real_split_boundary():
    tree = SimpleNamespace(children_left=np.array([1, -1, -1]), children_right=np.array([2, -1, -1]),
        feature=np.array([0, -2, -2]), threshold=np.array([.5, -2, -2]))
    assert manual_tree_leaves(tree, [[.1], [.5], [.50000000001], [.9]]).tolist() == [1, 1, 1, 2]


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e400}'])
def test_untrusted_json_rejected(tmp_path, text):
    path = tmp_path / "input.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        phase.read_json(path)


def test_frozen_hash_tamper_rejected(tmp_path):
    path = tmp_path / "fixture.txt"
    path.write_text("frozen", encoding="utf-8")
    hashes = {str(path): phase.digest_path(path)}
    phase.verify_hashes(hashes)
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError):
        phase.verify_hashes(hashes)


def test_bounded_split_plan_selection_reads_complete_named_plan(tmp_path):
    path = tmp_path / "splits.parquet"
    pd.DataFrame({"plan": ["authorized_2024_only"] * 10 + ["unselected"] * 100001,
                  "value": range(100011)}).to_parquet(path, index=False)
    with pytest.raises(ValueError):
        phase.bounded_frame(path, tmp_path)
    selected = phase.bounded_frame(path, tmp_path, filters=[("plan", "=", "authorized_2024_only")])
    assert len(selected) == 10 and selected.value.tolist() == list(range(10))


def test_no_training_calls_or_model_serialization_in_phase5e():
    for name in ("temporal_history.py", "temporal_feasibility.py", "temporal_model_a_audit.py", "temporal_feasibility_report.py"):
        parsed = ast.parse(Path(phase.__file__).with_name(name).read_text(encoding="utf-8"))
        for node in ast.walk(parsed):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"fit", "fit_transform", "partial_fit"}
                assert not (node.func.attr == "dump" and isinstance(node.func.value, ast.Name) and node.func.value.id == "joblib")


@pytest.mark.parametrize("destination", ["frontend/public/result", "backend/result", "data/processed/official", h.__name__])
def test_nonprivate_destination_rejected(tmp_path, destination):
    with pytest.raises(ValueError):
        phase.checked_output(tmp_path, destination)
