"""Valida estados existentes; no abre cartografía ni asigna radios."""

from .results import CheckResult as C, text


def validate_spatial(record):
    state, geometry = record.get("assignment_state"), record.get("geometry_status")
    candidate = record.get("radio_candidate")
    matches, reasons = record.get("matching_radios"), record.get("uncertainty_reasons")
    if state not in ("unique_geometry", "uncertain", "ambiguous", "unassigned"):
        return [C("spatial.state", "invalido", "Estado de asignación ausente o fuera del contrato.", "assignment_state")]
    if (not isinstance(matches, list) or not all(text(item) for item in matches)
            or len(matches) != len(set(matches)) or not isinstance(reasons, list)
            or not all(text(item) for item in reasons)):
        return [C("spatial.structure", "invalido", "Faltan candidatos o motivos de incertidumbre estructurados.", "matching_radios,uncertainty_reasons")]
    coherent = False
    if state in ("unique_geometry", "uncertain"):
        coherent = geometry == "unique_interior" and text(candidate) and matches == [candidate]
        coherent = coherent and (bool(reasons) if state == "uncertain" else not reasons)
    elif state == "ambiguous":
        coherent = candidate is None and ((geometry == "boundary" and len(matches) == 1)
                                          or (geometry == "multiple_matches" and len(matches) > 1))
    else:
        coherent = candidate is None and not matches and geometry in (
            "missing_coordinates", "invalid_coordinates", "unknown_crs", "outside_territory")
    results = [C("spatial.consistency", "valido" if coherent else "invalido",
                 "Estado geométrico y candidato coherentes." if coherent else "Asignación contradice la geometría o pierde incertidumbre.", "radio_candidate,geometry_status")]
    for field, value, reason in (("crs_confirmed", False, "crs_unconfirmed"),
                                 ("location_role", "unknown", "location_meaning_unknown")):
        if field in record and record[field] == value and reason not in reasons:
            results.append(C("spatial.reason", "invalido", "Se perdió un motivo de incertidumbre declarado.", "uncertainty_reasons"))
    if state != "unique_geometry":
        results.append(C("spatial.uncertainty", "pendiente_acreditacion" if state in ("ambiguous", "unassigned") else "advertencia",
                         "Conservar ambigüedad o incertidumbre; no elegir ni corregir un radio.", "assignment_state"))
    results.append(C("spatial.accreditation", "pendiente_acreditacion",
                     "La coincidencia geométrica no acredita residencia ni lugar de infección.", "epidemiological_precision_validated"))
    return results
