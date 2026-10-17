"""Grilla privada radio-semana; cuenta filas candidatas, no casos únicos validados."""

from collections import Counter, defaultdict

import pandas as pd

from sigard_ml.official.calendar import weeks_between
from sigard_ml.official.cartography import validate_radios
from sigard_ml.official.coverage import coverage_by_cell, observation_state
from sigard_ml.official.observed_settings import OBSERVED_VERSION, ROW_KEY
from sigard_ml.official.spatial_settings import SPATIAL_VERSION


def classify_processing_outcome(frame):
    """Un único desenlace por fila, conservando también todos sus motivos."""
    result, reasons = [], []
    for _, row in frame.iterrows():
        issues = []
        if row.analysis_eligibility == "excluded":
            outcome, issues = "excluded", [row.eligibility_reason]
        elif row.reference_date_status == "outside_analysis_period":
            outcome, issues = "excluded", ["outside_analysis_period"]
        elif row.episode_status == "resolved_nonrepresentative":
            outcome, issues = "excluded", ["reviewed_nonrepresentative"]
        else:
            if row.analysis_eligibility != "eligible_provisional":
                issues.append("eligibility_pending")
            if not row.identity_countable:
                issues.append("identity_pending")
            if not row.date_within_analysis_period:
                issues.append("date_unusable")
            if pd.isna(row.radio_candidate):
                issues.append("territory_unassignable")
            outcome = "pending" if issues else "included"
        result.append(outcome)
        reasons.append(issues)
    return pd.DataFrame({"processing_outcome": result, "processing_reasons": reasons})


def pending_counts(frame, radios, weeks):
    """Pendientes sin fecha/radio afectan todas las celdas posibles; no se imputan.

    Su número por celda es un diagnóstico de posible incompletitud: no se suma
    entre radios o semanas para obtener el total de filas pendientes.
    """
    cells, by_radio, by_week, global_pending = Counter(), Counter(), Counter(), 0
    radio_ids = set(radios)
    week_starts = {week.start for week in weeks}
    for _, row in frame.loc[frame.processing_outcome.eq("pending")].iterrows():
        radio, week = row.radio_candidate, row.week_start
        has_radio = pd.notna(radio) and radio in radio_ids
        has_week = pd.notna(week) and week in week_starts
        if has_radio and has_week:
            cells[radio, week] += 1
        elif has_radio:
            by_radio[radio] += 1
        elif has_week:
            by_week[week] += 1
        else:
            global_pending += 1
    return cells, by_radio, by_week, global_pending


def included_cells(frame):
    counts, uncertain, sources, categories = Counter(), Counter(), defaultdict(set), defaultdict(Counter)
    included = frame.loc[frame.processing_outcome.eq("included")]
    if included.episode_ref.duplicated().any() or included.duplicated(ROW_KEY).any():
        raise ValueError("Un registro o episodio candidato sería contabilizado dos veces")
    for _, row in included.iterrows():
        key = (row.radio_candidate, row.week_start)
        counts[key] += 1
        uncertain[key] += int(row.assignment_state == "uncertain")
        sources[key].add(row.source_id)
        categories[key][row.geocoding_category] += 1
    return counts, uncertain, sources, categories


def build_observed_panel(frame, radios, *, period_start, period_end, options,
                         exploratory=False, expected_count=263):
    validate_radios(radios, expected_count=expected_count)
    if frame.duplicated(ROW_KEY).any():
        raise ValueError("Filas de entrada repetidas")
    weeks = weeks_between(period_start, period_end)
    identifiers = sorted(radios.radio_id.tolist())
    fractions = {radio: radio[:7] for radio in identifiers}
    coverage = coverage_by_cell(options["coverage"], identifiers, weeks)
    counts, uncertain, sources, categories = included_cells(frame)
    cells, by_radio, by_week, global_pending = pending_counts(frame, identifiers, weeks)
    rows = []
    for radio in identifiers:
        for week in weeks:
            key = (radio, week.start)
            declared, evidence = coverage.get(key, ("unknown", None))
            pending = cells[key] + by_radio[radio] + by_week[week.start] + global_pending
            window_partial = week.start < period_start or week.end > period_end
            count, state, effective = observation_state(counts[key], pending, declared,
                                                        partial_window=window_partial)
            rows.append({"radio_censal": radio, "fraccion_censal": fractions[radio],
                         "anio_epidemiologico": week.year, "semana_epidemiologica": week.number,
                         "fecha_inicio_semana": week.start, "fecha_fin_semana": week.end,
                         "registros_elegibles_provisionales": count, "estado_observacion": state,
                         "cobertura_temporal": effective, "cobertura_declarada": declared,
                         "evidencia_cobertura": evidence, "ventana_semanal_parcial": window_partial,
                         "registros_pendientes_posibles": pending,
                         "registros_asignacion_incierta": uncertain[key],
                         "tipos_geocodificacion": sorted(categories[key]), "fuentes_con_registros": sorted(sources[key]),
                         "version_transformacion": OBSERVED_VERSION,
                         "version_asignacion_geografica": options.get("spatial_version", SPATIAL_VERSION),
                         "version_clasificacion": options["classification_version"],
                         "version_elegibilidad": options["eligibility_version"],
                         "version_episodios": options["episode_version"],
                         "version_fecha": options["date_rule_version"], "version_cobertura": options["coverage_version"],
                         "estado_panel": "exploratorio_provisional" if exploratory else "revision_conservadora",
                         "validado": False, "apto_entrenamiento": False,
                         "disponibilidad_historica": "no_reconstruida"})
    panel = pd.DataFrame(rows)
    panel["registros_elegibles_provisionales"] = panel.registros_elegibles_provisionales.astype("Int64")
    validate_observed_panel(panel, identifiers, weeks, int(frame.processing_outcome.eq("included").sum()))
    return panel


def validate_observed_panel(panel, identifiers, weeks, included_rows):
    keys = ["radio_censal", "fecha_inicio_semana"]
    expected = {(radio, week.start) for radio in identifiers for week in weeks}
    actual = set(panel[keys].itertuples(index=False, name=None))
    if (len(panel) != len(identifiers) * len(weeks) or panel.duplicated(keys).any()
            or actual != expected):
        raise ValueError("Grilla temporal o territorial incompleta")
    if not panel.radio_censal.map(lambda value: isinstance(value, str)).all():
        raise ValueError("Los identificadores censales deben conservarse como cadenas")
    counts = panel.registros_elegibles_provisionales
    if counts.dropna().lt(0).any() or int(counts.sum()) != included_rows:
        raise ValueError("Los conteos del panel no concilian con las filas incluidas")
    zeros = counts.eq(0).fillna(False)
    if not panel.loc[zeros, "estado_observacion"].eq("cero_con_cobertura_comprobada").all():
        raise ValueError("Cero sin cobertura comprobada")
    if not panel.loc[zeros, "cobertura_temporal"].eq("complete").all():
        raise ValueError("Cero sin cobertura completa")
    absent = panel.estado_observacion.isin(["sin_informacion_suficiente", "fuera_de_cobertura"])
    if panel.loc[absent, "registros_elegibles_provisionales"].notna().any():
        raise ValueError("Una ausencia no puede tener conteo")
    if panel.validado.any() or panel.apto_entrenamiento.any():
        raise ValueError("Este constructor produce exclusivamente un panel provisional")
