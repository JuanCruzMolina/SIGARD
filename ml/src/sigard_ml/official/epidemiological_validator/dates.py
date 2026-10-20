"""Comprueba referencias ya seleccionadas, sin seleccionar respaldos ni imputar."""

from sigard_ml.official.calendar_rules import CALENDAR_VERSION, DEFAULT_CALENDAR, CalendarError
from sigard_ml.official.observed_dates import DATE_HIERARCHY, DATE_TYPES, parse_reference_date
from .results import CheckResult as C, text


def validate_week_fields(row, *, year_field, number_field, start_field, end_field):
    if row.get("calendar_version") != CALENDAR_VERSION:
        return [C("date.calendar", "invalido", "Falta la versión argentina vigente; no reinterpretar claves históricas.", "calendar_version")]
    try:
        start, end = DEFAULT_CALENDAR.week_bounds(row.get(year_field), row.get(number_field))
    except CalendarError:
        return [C("date.week", "invalido", "Año no respaldado o semana inexistente en el calendario argentino.", number_field)]
    if any(parse_reference_date(row.get(field))[0] != expected
           for field, expected in ((start_field, start), (end_field, end))):
        return [C("date.week", "invalido", "Límites incompatibles con la semana argentina domingo–sábado.", start_field + "," + end_field)]
    return [C("date.week", "valido", "Semana consistente con el calendario argentino versionado.", number_field)]


def validate_dates(record):
    results, parsed = [], {}
    for field in DATE_HIERARCHY:
        value, state = parse_reference_date(record.get(field))
        parsed[field] = value
        results.append(C("date." + field, "valido" if state == "valid" else "advertencia" if state == "missing" else "invalido",
                         "Fecha consignada utilizable; no acredita su significado clínico." if state == "valid" else
                         "Fecha faltante; no imputar." if state == "missing" else "Formato de fecha inválido, ambiguo o fuera de rango.", field))
        if field + "_status" in record and (record[field + "_status"] == "valid") != (state == "valid"):
            results.append(C("date.source_status", "invalido", "La fecha contradice su estado de normalización.", field + "_status"))
    if parsed["symptom_onset"] and parsed["sample_on"] and parsed["sample_on"] < parsed["symptom_onset"]:
        results.append(C("date.chronology", "advertencia", "Muestra anterior a síntomas consignados; requiere revisión, sin corrección clínica automática.", "sample_on,symptom_onset"))
    reference, state = parse_reference_date(record.get("reference_date"))
    if state != "valid":
        results.append(C("date.reference", "pendiente_acreditacion" if state == "missing" else "invalido",
                         "Referencia epidemiológica ausente o no utilizable; no asignar semana.", "reference_date"))
        if any(record.get(name) is not None for name in ("week_start", "week_end", "epidemiological_year", "epidemiological_week")):
            results.append(C("date.week", "invalido", "Semana asignada sin fecha de referencia utilizable.", "week_start"))
        return results
    field = record.get("reference_date_field")
    if not isinstance(field, str):
        return results + [C("date.reference", "invalido", "Campo temporal ausente o inválido.", "reference_date_field")]
    if field not in DATE_HIERARCHY or reference != parsed.get(field):
        results.append(C("date.reference", "invalido", "Referencia incompatible con su campo declarado.", "reference_date_field"))
    if not text(record.get("date_rule_version")):
        results.append(C("date.rule", "invalido", "Falta versión de selección temporal.", "date_rule_version"))
    approximate = field in DATE_HIERARCHY and field != "symptom_onset"
    if type(record.get("fecha_aproximada")) is not bool or record["fecha_aproximada"] != approximate:
        results.append(C("date.approximation", "invalido", "Debe conservarse si la referencia es alternativa a síntomas.", "fecha_aproximada"))
    else:
        results.append(C("date.approximation", "advertencia" if approximate else "valido",
                         "Referencia alternativa; no representa inicio confirmado de síntomas." if approximate else "Referencia de inicio de síntomas consignada.", "fecha_aproximada"))
    if "tipo_fecha_referencia" in record and record["tipo_fecha_referencia"] != DATE_TYPES.get(field):
        results.append(C("date.type", "invalido", "Tipo de fecha incompatible con el campo seleccionado.", "tipo_fecha_referencia"))
    if "fecha_referencia" in record and parse_reference_date(record["fecha_referencia"])[0] != reference:
        results.append(C("date.reference_alias", "invalido", "Las referencias temporales duplicadas no coinciden.", "fecha_referencia"))
    results += validate_week_fields(record, year_field="epidemiological_year", number_field="epidemiological_week",
                                    start_field="week_start", end_field="week_end")
    try:
        expected = DEFAULT_CALENDAR.date_week(reference)
        if expected != (record.get("epidemiological_year"), record.get("epidemiological_week")):
            results.append(C("date.reference_week", "invalido", "La referencia pertenece a otra semana epidemiológica.", "epidemiological_week"))
    except CalendarError:
        results.append(C("date.reference_week", "invalido", "Fecha fuera del calendario respaldado; no extrapolar.", "reference_date"))
    return results
