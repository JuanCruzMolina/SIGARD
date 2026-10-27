"""Selección temporal trazable. El respaldo sólo se activa con jerarquía explícita."""

from datetime import date, datetime
import re

import pandas as pd

from sigard_ml.official.calendar import week_from_date
from sigard_ml.official.settings import DATE_FIELDS
from sigard_ml.official.normalization import DATE_FORMATS, normalize_text
from sigard_ml.official.settings import DATE_MIN_YEAR, DATE_MAX_YEAR, normalize_header

DATE_HIERARCHY = ("symptom_onset", "consultation_on", "sample_on", "notified_on")
# Opción explícita para conteos principales; no cambia escenarios congelados.
PRINCIPAL_DATE_HIERARCHY = ("symptom_onset", "sample_on")
DATE_TYPES = dict(zip(DATE_HIERARCHY, ("inicio_sintomas", "consulta_medica", "toma_muestra", "notificacion")))
# Correspondencias literales. Apertura, actualización, revisión administrativa,
# fecha de edición del libro y query del geocodificador no son fechas clínicas.
REFERENCE_HEADERS = {
    "symptom_onset": ("fecha de inicio de sintomas", "fecha inicio sintomas", "fecha inicio de sintomas", "fis"),
    "consultation_on": ("fecha de consulta medica", "fecha consulta medica"),
    "sample_on": ("fecha de toma de muestra", "fecha toma muestra", "fecha toma de muestra"),
    "notified_on": ("fecha de notificacion", "fecha notificacion"),
}


def validate_date_hierarchy(hierarchy):
    if (not isinstance(hierarchy, (list, tuple)) or not hierarchy
            or (tuple(hierarchy) != DATE_HIERARCHY[:len(hierarchy)]
                and tuple(hierarchy) != PRINCIPAL_DATE_HIERARCHY)):
        raise ValueError("La jerarquía debe ser un prefijo de síntomas, consulta, muestra, notificación o síntomas, muestra")


def identify_reference_header(header):
    label = normalize_header(header)
    return next((field for field, aliases in REFERENCE_HEADERS.items() if label in aliases), None)


def parse_reference_date(value, formats=DATE_FORMATS):
    """Formatos explícitos; sin seriales, años abreviados, fórmulas ni inferencia."""
    if normalize_text(value) is None or value is pd.NaT:
        return None, "missing"
    if isinstance(value, (datetime, date)):
        parsed = value.date() if isinstance(value, datetime) else value
    elif isinstance(value, str):
        candidates = set()
        for pattern in formats:
            try:
                candidates.add(datetime.strptime(value.strip(), pattern).date())
            except ValueError:
                continue
        if len(candidates) > 1 or re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2}", value.strip()):
            return None, "ambiguous_date"
        if not candidates:
            return None, "invalid_format"
        parsed = candidates.pop()
    else:
        return None, "invalid_format"
    if not DATE_MIN_YEAR <= parsed.year <= DATE_MAX_YEAR:
        return None, "out_of_range"
    return parsed, "valid"


def original_date_text(value):
    """Texto sin limpiar; fechas nativas en ISO y tipo separado para reconstrucción."""
    if value is None or value is pd.NaT or (isinstance(value, float) and pd.isna(value)):
        return None
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def select_reference_date(record, hierarchy, period_start, period_end, as_of):
    rejections = []
    for field in hierarchy:
        value, status = record.get(field), record.get(field + "_status", "missing")
        if pd.isna(status):
            status = "missing"
        if status == "valid":
            value, status = parse_reference_date(value)
        if status == "valid":
            if value > as_of:
                status = "future_date"
            elif not period_start <= value <= period_end:
                status = "outside_analysis_period"
        if status == "valid":
            return value, field, rejections
        rejections.append(f"{field}:{status}")
        if tuple(hierarchy) == PRINCIPAL_DATE_HIERARCHY and status in {"future_date", "outside_analysis_period"}:
            # Una fecha interpretable no se sustituye para hacer entrar la fila
            # en la ventana. El alcance/contradicción requiere revisión.
            return None, None, rejections
    return None, None, rejections


def assign_hierarchy_weeks(frame, *, hierarchy, period_start, period_end, as_of, version):
    validate_date_hierarchy(hierarchy)
    if not version or not period_start <= period_end <= as_of:
        raise ValueError("Regla temporal o período inválidos")
    rows, cache = [], {}
    for _, record in frame.iterrows():
        value, field, rejections = select_reference_date(record, hierarchy, period_start, period_end, as_of)
        if value is not None and value not in cache:
            cache[value] = week_from_date(value)
        week = cache.get(value)
        approximate = field is not None and field != "symptom_onset"
        reason = ("primera_fecha_valida_en_jerarquia" if not rejections else "respaldo_tras_fecha_no_disponible") if field else "ninguna_fecha_valida"
        rows.append({"reference_date": value, "reference_date_status": "valid" if field else "no_valid_reference_date",
            "reference_date_usable": field is not None, "date_within_analysis_period": field is not None,
            "week_start": week.start if week else None, "week_end": week.end if week else None,
            "epidemiological_year": week.year if week else None, "epidemiological_week": week.number if week else None,
            "reference_date_field": field, "date_rule_version": version,
            "fecha_referencia": value, "tipo_fecha_referencia": DATE_TYPES.get(field),
            "fecha_aproximada": approximate, "motivo_seleccion_fecha": reason,
            "date_selection_rejections": rejections,
            "semana_potencialmente_afectada_por_retraso": approximate})
    return pd.DataFrame(rows)


def assign_record_weeks(frame, *, field, period_start, period_end, as_of, version, hierarchy=None):
    if hierarchy is not None:
        return assign_hierarchy_weeks(frame, hierarchy=hierarchy, period_start=period_start,
                                      period_end=period_end, as_of=as_of, version=version)
    if field not in DATE_FIELDS or not version or not period_start <= period_end <= as_of:
        raise ValueError("Regla temporal o período inválidos")
    rows, week_cache = [], {}
    for _, record in frame.iterrows():
        value, status = record.get(field), record.get(field + "_status", "missing")
        if pd.isna(status):
            status = "missing"
        usable = status == "valid" and value is not None and not pd.isna(value)
        if usable:
            value = pd.Timestamp(value).date()
            if not 1678 <= value.year <= 2260:
                status, usable = "outside_calendar_range", False
            elif value > as_of:
                status, usable = "future_date", False
        within = usable and period_start <= value <= period_end
        week = None
        if within:
            if value not in week_cache:
                week_cache[value] = week_from_date(value)
            week = week_cache[value]
        if usable and not within:
            status = "outside_analysis_period"
        rows.append({"reference_date": value if usable else None, "reference_date_status": status,
                     "reference_date_usable": bool(usable), "date_within_analysis_period": bool(within),
                     "week_start": week.start if week else None, "week_end": week.end if week else None,
                     "epidemiological_year": week.year if week else None,
                     "epidemiological_week": week.number if week else None,
                     "reference_date_field": field, "date_rule_version": version,
                     "fecha_referencia": value if usable else None,
                     "tipo_fecha_referencia": DATE_TYPES.get(field) if within else None,
                     "fecha_aproximada": bool(within and field != "symptom_onset"),
                     "motivo_seleccion_fecha": "campo_unico_estricto" if within else "fecha_no_utilizable",
                     "date_selection_rejections": [] if within else [f"{field}:{status}"],
                     "semana_potencialmente_afectada_por_retraso": bool(within and field != "symptom_onset")})
    return pd.DataFrame(rows)
