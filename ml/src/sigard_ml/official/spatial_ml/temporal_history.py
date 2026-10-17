"""Fase 5E: historia de registros y presencia experimental, sin imputar ceros."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from sigard_ml.official.spatial_ml.features import KEYS

START, END = date(2024, 1, 7), date(2024, 6, 8)
PARTS = ("train", "validation", "test")
TRACKS = ("presencia_exp", "registros_provisionales", "registros_sin_pendientes")
LAGS, WINDOWS = (1, 2, 3, 4), (4, 8)


def source_history(weekly, labels, context):
    """La fecha de una etiqueta t+1 pasa a ser la semana FUENTE, nunca t."""
    for frame in (weekly, context):
        if frame.duplicated(KEYS).any() or frame[KEYS].isna().any().any():
            raise ValueError("Identidad semanal inválida")
    scope = labels[labels.en_intervalo_autorizado.eq(True)].copy()
    targets = scope[["radio_censal", "fecha_inicio_semana_objetivo", "objetivo_semana_siguiente", "tipo_etiqueta"]].rename(
        columns={"fecha_inicio_semana_objetivo": "fecha_inicio_semana", "objetivo_semana_siguiente": "presencia_exp"})
    if targets.duplicated(KEYS).any():
        raise ValueError("Etiqueta duplicada para una semana fuente")
    result = weekly.merge(targets, on=KEYS, how="inner", validate="one_to_one")
    details = context[KEYS + ["estado_cobertura", "estado_observacion", "cobertura_comprobada",
        "registros_fecha_aproximada", "registros_asignacion_incierta", "version_fecha", "version_transformacion"]]
    result = result.merge(details, on=KEYS, how="left", validate="one_to_one")
    if (result.empty or result.fecha_inicio_semana.min() != START or result.fecha_fin_semana.max() != END
            or not result.en_intervalo_autorizado.eq(True).all()
            or not result.fecha_fin_semana.eq(result.fecha_inicio_semana.map(lambda x: x + timedelta(days=6))).all()):
        raise ValueError("Historia fuera del intervalo autorizado")
    if result[["estado_cobertura", "estado_observacion", "cobertura_comprobada",
               "registros_fecha_aproximada", "version_fecha", "version_transformacion"]].isna().any().any():
        raise ValueError("Procedencia semanal incompleta")
    y, count = result.presencia_exp, result.casos_observados
    if (not y.dropna().isin([0, 1]).all() or count.dropna().lt(0).any()
            or result.registros_pendientes_posibles.isna().any()):
        raise ValueError("Valor semanal inválido")
    positive = y.eq(1).fillna(False)
    zero = y.eq(0).fillna(False)
    unknown = y.isna()
    if (not result.loc[positive, "tipo_etiqueta"].eq("positivo_provisional").all()
            or result.loc[positive, "casos_observados"].isna().any()
            or not result.loc[positive, "casos_observados"].gt(0).fillna(False).all()
            or not result.loc[zero, "tipo_etiqueta"].eq("cero_asumido_experimental").all()
            or not result.loc[zero, "ausencia_asumida_autorizada"].eq(True).all()
            or result.loc[zero, "casos_observados"].notna().any()
            or not result.loc[zero, "registros_pendientes_posibles"].eq(0).all()
            or not result.loc[zero, "ventana_semanal_parcial"].eq(False).all()
            or not result.loc[unknown, "tipo_etiqueta"].eq("desconocida").all()):
        raise ValueError("No concilian etiquetas, supuestos o bloqueos")
    result["presencia_exp"] = y.astype("Int8")
    # Ningún null de casos_observados se transforma en cero, ni en un proxy de conteo.
    result["registros_provisionales"] = count.astype("Int64")
    result["registros_sin_pendientes"] = count.where(result.registros_pendientes_posibles.eq(0)).astype("Int64")
    result["fuente_cero_asumido"] = zero
    result["fuente_pendientes"] = result.registros_pendientes_posibles.gt(0)
    result["fuente_fecha_aproximada"] = result.registros_fecha_aproximada.gt(0)
    result["fuente_desconocida"] = unknown
    result["disponibilidad_en_origen_acreditada"] = False
    result["estado_disponibilidad_historica"] = "no_acreditada"
    pd.testing.assert_series_equal(result.registros_provisionales, result.casos_observados, check_names=False)
    return result.sort_values(KEYS).reset_index(drop=True)


def validate_neighbors(neighbors, radio_ids):
    if set(neighbors) != set(radio_ids):
        raise ValueError("Universo vecinal diferente de la grilla")
    for radio, adjacent in neighbors.items():
        if (radio in adjacent or len(adjacent) != len(set(adjacent)) or not set(adjacent) <= set(neighbors)
                or any(radio not in neighbors[other] for other in adjacent)):
            raise ValueError("Vecindad inválida, duplicada o asimétrica")


def weekly_neighbor_series(source, neighbors, column):
    """Suma sólo con TODOS los vecinos conocidos; no hay vecinos => desconocido."""
    weeks = sorted(source.fecha_inicio_semana.unique())
    pivot = source.pivot(index="fecha_inicio_semana", columns="radio_censal", values=column).reindex(weeks)
    values, flags = {}, {}
    for radio, adjacent in sorted(neighbors.items()):
        if adjacent:
            block = pivot.reindex(columns=adjacent)
            sums = block.sum(axis=1, min_count=len(adjacent))
            present = block.notna().sum(axis=1)
        else:
            sums = pd.Series(np.nan, index=weeks)
            present = pd.Series(0, index=weeks)
        for week in weeks:
            values[radio, week] = sums.loc[week]
            flags[radio, week] = int(present.loc[week])
    index = pd.MultiIndex.from_tuples(sorted(values), names=KEYS)
    series = pd.Series(pd.array([values[key] for key in index], dtype="Int64"), index=index)
    known = pd.Series([flags[key] for key in index], index=index, dtype="int64")
    return series, known


def lookup(values, prediction_keys, lag):
    if type(lag) is not int or lag < 1:
        raise ValueError("Los rezagos deben ser estrictamente anteriores al origen")
    dates = prediction_keys.fecha_inicio_semana.map(lambda day: day - timedelta(weeks=lag))
    index = pd.MultiIndex.from_arrays([prediction_keys.radio_censal, dates], names=KEYS)
    return pd.Series(pd.array(values.reindex(index).to_numpy(), dtype="Int64"), index=prediction_keys.index)


def history_matrix(source, prediction_keys, neighbors):
    """Offsets exactos [t-W,t-1]; los huecos no se saltan."""
    prediction_keys = prediction_keys[KEYS].sort_values(KEYS).reset_index(drop=True)
    if prediction_keys.duplicated(KEYS).any() or source.duplicated(KEYS).any():
        raise ValueError("Claves duplicadas en historia o predicción")
    validate_neighbors(neighbors, source.radio_censal.unique())
    result = {name: prediction_keys[name] for name in KEYS}
    catalog = []
    index = pd.MultiIndex.from_frame(source[KEYS])
    meta = pd.DataFrame(index=prediction_keys.index)
    for name in ("fuente_cero_asumido", "fuente_pendientes", "fuente_fecha_aproximada", "fuente_desconocida"):
        values = pd.Series(source[name].astype(int).to_numpy(), index=index)
        for lag in range(1, 9):
            meta[name + f"_lag_{lag}"] = lookup(values, prediction_keys, lag)
    for scope in ("local", "vecinos"):
        for track in TRACKS:
            if scope == "local":
                values = pd.Series(source[track].array, index=index)
            else:
                values, _ = weekly_neighbor_series(source, neighbors, track)
            block = pd.DataFrame({lag: lookup(values, prediction_keys, lag) for lag in range(1, 9)})
            names = []
            for lag in LAGS:
                name = f"{scope}_{track}_rezago_{lag}"
                result[name] = block[lag]
                names.append((name, [-lag]))
            for window in WINDOWS:
                name = f"{scope}_{track}_acumulado_{window}"
                result[name] = block[list(range(1, window + 1))].sum(axis=1, min_count=window).astype("Int64")
                names.append((name, list(range(-window, 0))))
                result[f"{scope}_{track}_semanas_con_valor_{window}"] = block[list(range(1, window + 1))].notna().sum(axis=1).astype("int8")
            for name, offsets in names:
                result[name + "_valor_disponible"] = result[name].notna()
                result[name + "_disponibilidad_operativa_acreditada"] = False
                catalog.append({"feature": name, "scope": scope, "track": track, "source_week_offsets": offsets,
                    "maximum_source_week_offset": max(offsets), "uses_target_or_future_week": False,
                    "unit": ("positive_radio_weeks" if scope == "local" else "positive_neighbor_radio_weeks")
                        if track == "presencia_exp" else "recorded_provisional_records_not_verified_cases",
                    "missing_policy": "NaN if any required week or neighbor unknown; exact weekly keys",
                    "zeros": "existing experimental absence labels only; no count null is replaced with zero"
                        if track == "presencia_exp" else "no assumed zeros; original recorded counts only",
                    "point_in_time_availability": "unverified; operational value masked",
                    "source_kind": "provisional_positives_assumed_negatives_unknowns" if track == "presencia_exp" else "provisional_recorded_counts",
                    "requires_all_neighbors": scope == "vecinos"})
    for window in WINDOWS:
        for flag in ("fuente_cero_asumido", "fuente_pendientes", "fuente_fecha_aproximada", "fuente_desconocida"):
            columns = [flag + f"_lag_{lag}" for lag in range(1, window + 1)]
            # Cuentan banderas conocidas, no casos; se informa por separado el soporte fuente.
            result[f"local_{flag}_celdas_{window}"] = meta[columns].sum(axis=1, min_count=1).astype("Int64")
        result[f"local_semanas_fuente_dentro_escenario_{window}"] = meta[
            ["fuente_cero_asumido" + f"_lag_{lag}" for lag in range(1, window + 1)]].notna().sum(axis=1).astype("int8")
    result = pd.DataFrame(result)
    values = [row["feature"] for row in catalog]
    operational = result[KEYS].copy()
    for name in values:
        operational[name] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        operational[name + "_valor_disponible"] = False
    return result, operational, catalog


def availability_report(matrix, prediction_labels, catalog):
    labels = prediction_labels[KEYS + ["partition", "fecha_inicio_semana_objetivo", "objetivo_semana_siguiente"]]
    if labels.duplicated(KEYS).any():
        raise ValueError("Etiquetas de evaluación duplicadas")
    joined = matrix.merge(labels, on=KEYS, validate="one_to_one")
    rows, weeks = [], []
    specifications = [(r["feature"], [r["feature"]], r["scope"], r["track"]) for r in catalog]
    for scope in ("local", "vecinos"):
        for track in TRACKS:
            names = [f"{scope}_{track}_rezago_{lag}" for lag in LAGS]
            specifications.append((f"{scope}_{track}_rezagos_1_a_4_conjuntos", names, scope, track))
    for part in PARTS:
        group = joined[joined.partition.eq(part)]
        known_target = group.objetivo_semana_siguiente.notna()
        for name, features, scope, track in specifications:
            available = group[features].notna().all(axis=1)
            used = group[available]
            positive = used.objetivo_semana_siguiente.eq(1).fillna(False)
            negative = used.objetivo_semana_siguiente.eq(0).fillna(False)
            per_week = []
            for target, cell in used.groupby("fecha_inicio_semana_objetivo", sort=True):
                pos, neg = int(cell.objetivo_semana_siguiente.eq(1).sum()), int(cell.objetivo_semana_siguiente.eq(0).sum())
                per_week.append({"partition": part, "feature_or_set": name, "target_week": str(target),
                    "rows_feature_known": len(cell), "target_positive": pos, "target_negative": neg,
                    "target_unknown": int(cell.objetivo_semana_siguiente.isna().sum())})
            rows.append({"partition": part, "scope": scope, "track": track, "feature_or_set": name,
                "grid_rows": len(group), "known_targets": int(known_target.sum()),
                "rows_feature_known": int(available.sum()), "fraction_grid_available": float(available.mean()),
                "rows_feature_and_target_known": int((available & known_target).sum()),
                "target_positive_when_feature_known": int(positive.sum()),
                "target_negative_when_feature_known": int(negative.sum()),
                "target_unknown_when_feature_known": int(used.objetivo_semana_siguiente.isna().sum()),
                "distinct_origin_weeks_feature_known": int(used.fecha_inicio_semana.nunique()),
                "distinct_target_weeks_feature_known": len(per_week),
                "target_weeks_with_both_classes_and_feature": sum(row["target_positive"] > 0 and row["target_negative"] > 0 for row in per_week),
                "operational_rows_available": 0,
                "rows_retained_with_missing_features": int((~available).sum())})
            weeks.extend(per_week)
    return pd.DataFrame(rows), pd.DataFrame(weeks)


def pending_report(source, matrix, prediction_labels):
    scope = prediction_labels[prediction_labels.partition.isin(PARTS)]
    joined = matrix.merge(scope[KEYS + ["partition", "objetivo_semana_siguiente"]], on=KEYS, validate="one_to_one")
    rows = []
    for part in PARTS:
        group = joined[joined.partition.eq(part)]
        for window in WINDOWS:
            complete = group[f"local_presencia_exp_acumulado_{window}"].notna()
            strict = group[f"local_registros_sin_pendientes_acumulado_{window}"].notna()
            pending = group[f"local_fuente_pendientes_celdas_{window}"].gt(0).fillna(False)
            unknown = group[f"local_fuente_desconocida_celdas_{window}"].gt(0).fillna(False)
            rows.append({"partition": part, "window": window, "rows": len(group),
                "rows_history_contains_pending": int(pending.sum()),
                "rows_history_contains_unknown": int(unknown.sum()),
                "rows_binary_complete_despite_pending_positives": int((complete & pending).sum()),
                "rows_binary_complete": int(complete.sum()), "rows_counts_complete_without_pending": int(strict.sum()),
                "rows_window_inside_authorized_scope": int(group[f"local_semanas_fuente_dentro_escenario_{window}"].eq(window).sum())})
    kinds = source.groupby("tipo_etiqueta", dropna=False).agg(cells=("radio_censal", "size"),
        with_pending=("fuente_pendientes", "sum"), recorded_counts_known=("registros_provisionales", "count")).reset_index()
    return pd.DataFrame(rows), kinds
