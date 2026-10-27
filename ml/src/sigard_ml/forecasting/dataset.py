"""Panel completo por radio/origen; joins de fechas exactas y snapshots as-of."""

from datetime import timedelta
from copy import deepcopy
import math

import numpy as np
import pandas as pd

from sigard_ml.forecasting import VERSION
from sigard_ml.forecasting.contracts import day, experimental, require, snapshot_scenario, usable_count, week
from sigard_ml.official.calendar_rules import CALENDAR_VERSION, DEFAULT_CALENDAR

COUNT_FEATURES = tuple(f"cases_lag_{lag}" for lag in range(1, 5))
CLIMATE_FEATURES = ("temperature_lag_1", "humidity_lag_1", "precipitation_lag_1",
                    "temperature_mean_4", "humidity_mean_4", "precipitation_sum_4")
FEATURES = (*COUNT_FEATURES, "cases_mean_4", "cases_trend_1", "neighbor_cases_mean_lag_1",
            *CLIMATE_FEATURES, "population", "area_km2", "population_density", "neighbor_count",
            "origin_year", "origin_week_number", "season_sin", "season_cos")


def snapshots(frame, keys, cutoff):
    """Primero última versión conocida; después se evalúa su elegibilidad."""
    available = frame.loc[frame.available_on.le(cutoff)]
    latest = available.sort_values("available_on").drop_duplicates(keys, keep="last")
    return {tuple(getattr(row, key) for key in keys): row for row in latest.itertuples()}


def input_snapshots(inputs, frame, keys, cutoff):
    """Exportación retrospectiva única o snapshots históricos; no mezcla políticas.

    La primera conserva available_on desconocido. No afirma disponibilidad en
    el origen: los rezagos/objetivos siguen seleccionándose por semana exacta.
    """
    if experimental(inputs):
        return {tuple(getattr(row, key) for key in keys): row for row in frame.itertuples()}
    return snapshots(frame, keys, cutoff)


def _date_text(value):
    return value.isoformat() if value is not None else None


def _count(inputs, lookup, radio, source_week):
    row = lookup.get((radio, source_week))
    return float(row.count) if usable_count(inputs, row) else np.nan


def build_dataset(inputs, *, start, end, evaluation_as_of, include_outcomes=True, horizon_weeks=1, origin_weeks=None):
    """evaluation_as_of congela desenlaces; nunca aporta semanas futuras a features.

    Origen t = domingo de la semana; cutoff = sábado al cierre. Todas las
    ventanas históricas excluyen t y usan t-1…t-4 para no asumir maduración.
    include_outcomes=False construye sólo features para inferencia: nunca lee
    etiquetas del objetivo ni exige que una semana futura esté en el paquete.
    La modalidad provisional usa la exportación retrospectiva única autorizada,
    conserva disponibilidad desconocida y no representa un backtest operativo.
    """
    inputs.validate()
    week(start)
    week(end)
    day(evaluation_as_of)
    require(type(include_outcomes) is bool, "La selección de desenlaces debe ser explícita")
    require(type(horizon_weeks) is int and horizon_weeks in (1, 2, 4), "Horizonte no soportado")
    require(start <= end, "Intervalo invertido")
    if hasattr(inputs, "validate_window"):
        inputs.validate_window(start, end, evaluation_as_of, include_outcomes=include_outcomes, horizon_weeks=horizon_weeks)
    require(evaluation_as_of >= end + timedelta(days=6), "Congelamiento anterior al origen")
    labels = input_snapshots(inputs, inputs.counts, ["radio_id", "week_start"], evaluation_as_of) if include_outcomes else {}
    rows = []
    origins = list(origin_weeks) if origin_weeks is not None else [start + timedelta(weeks=i) for i in range((end-start).days // 7 + 1)]
    require(origins and len(set(origins)) == len(origins) and all(start <= week_start <= end for week_start in origins), "Orígenes vacíos, duplicados o fuera de ventana")
    for origin in sorted(origins):
        year, number = week(origin)
        cutoff, target = origin + timedelta(days=6), origin + timedelta(weeks=horizon_weeks)
        target_year, target_number = week(target)
        counts = input_snapshots(inputs, inputs.counts, ["radio_id", "week_start"], cutoff)
        climate = input_snapshots(inputs, inputs.climate, ["week_start"], cutoff)
        territory = input_snapshots(inputs, inputs.territory, ["radio_id"], cutoff)
        past = [origin - timedelta(weeks=lag) for lag in range(1, 5)]
        graph_known = experimental(inputs) or inputs.graph_available_on <= cutoff
        for radio in sorted(inputs.radios):
            values = [_count(inputs, counts, radio, source_week) for source_week in past]
            context = territory.get((radio,))
            neighbors = [right for left, right in inputs.edges if left == radio] if graph_known else []
            neighbor_values = [_count(inputs, counts, neighbor, past[0]) for neighbor in neighbors]
            target_row = labels.get((radio, target))
            target_known = usable_count(inputs, target_row) and evaluation_as_of >= target + timedelta(days=6)
            row = dict(zip(COUNT_FEATURES, values))
            row.update(cases_mean_4=float(np.mean(values)), cases_trend_1=values[0] - values[1],
                       neighbor_cases_mean_lag_1=float(np.mean(neighbor_values)) if neighbors else np.nan)
            for field, aggregate in (("temperature", "mean"), ("humidity", "mean"), ("precipitation", "sum")):
                history = [climate.get((source_week,)) for source_week in past]
                observed = [float(getattr(item, field)) if item is not None and item.complete
                            and item.week_start + timedelta(days=6) <= cutoff
                            and pd.notna(getattr(item, field)) else np.nan for item in history]
                row[f"{field}_lag_1"] = observed[0]
                row[f"{field}_{aggregate}_4"] = float(np.mean(observed) if aggregate == "mean" else np.sum(observed))
            population = float(context.population) if context is not None and pd.notna(context.population) else np.nan
            area = float(context.area_km2) if context is not None and pd.notna(context.area_km2) else np.nan
            period = next(entry.weeks for entry in DEFAULT_CALENDAR.years if entry.year == year)
            row.update(population=population, area_km2=area, population_density=population / area,
                       neighbor_count=len(neighbors) if graph_known else np.nan,
                       origin_year=year, origin_week_number=number,
                       season_sin=math.sin(2 * math.pi * (number - 1) / period),
                       season_cos=math.cos(2 * math.pi * (number - 1) / period))
            for feature in FEATURES:
                row[feature + "_available"] = bool(pd.notna(row[feature]))
            row.update(radio_id=radio, origin_week=origin, cutoff_date=cutoff,
                       target_week=target, target_end=target + timedelta(days=6),
                       target_year=target_year, target_week_number=target_number,
                       target_count=float(target_row.count) if target_known else np.nan,
                       target_presence=int(target_row.count > 0) if target_known else np.nan,
                       target_available_on=target_row.available_on if target_known else None,
                       target_snapshot_available_on=target_row.available_on if target_row else None,
                       target_coverage_complete=bool(target_row.coverage_complete) if target_row else None,
                       target_pending=bool(target_row.pending) if target_row else None,
                       target_mature=bool(target_row.mature) if target_row else None,
                       target_state=("snapshot_record_count" if snapshot_scenario(inputs) else "observed_provisional_record_count" if experimental(inputs) else
                                     "complete_fictional" if inputs.data_kind == "fictional" else "complete_accredited") if target_known else "unknown",
                       target_input_state=target_row.state if target_row else "missing_snapshot",
                       data_kind=inputs.data_kind, target_unit=inputs.count_unit, dataset_version=inputs.dataset_version,
                       transformation_version=VERSION, calendar_version=CALENDAR_VERSION,
                       provenance={
                           "counts": [dict(week=source_week.isoformat(), source_ref=item.source_ref,
                                           available_on=_date_text(item.available_on), state=item.state,
                                           coverage_complete=bool(item.coverage_complete), pending=bool(item.pending), mature=bool(item.mature),
                                           usable=bool(usable_count(inputs, item)))
                                      for source_week in past if (item := counts.get((radio, source_week))) is not None],
                           "climate": [dict(week=source_week.isoformat(), source_ref=item.source_ref,
                                            available_on=_date_text(item.available_on), complete=bool(item.complete))
                                       for source_week in past if (item := climate.get((source_week,))) is not None],
                           "territory": context.source_ref if context else None,
                           "territory_available_on": _date_text(context.available_on) if context else None,
                           "graph": inputs.graph_ref if graph_known else None,
                           "neighbors": [dict(radio_id=neighbor, source_ref=item.source_ref,
                                              available_on=_date_text(item.available_on), usable=bool(usable_count(inputs, item)))
                                         for neighbor in neighbors if (item := counts.get((neighbor, past[0]))) is not None],
                           "target": target_row.source_ref if target_row else None,
                           "outcome_freeze": evaluation_as_of.isoformat(),
                       })
            rows.append(row)
    if hasattr(inputs, "input_evidence"):
        for row in rows:
            row["provenance"]["input_evidence"] = deepcopy(inputs.input_evidence)
    return pd.DataFrame(rows)
