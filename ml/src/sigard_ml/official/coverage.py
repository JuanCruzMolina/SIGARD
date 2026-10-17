"""Cobertura declarada con evidencia; ausencia de filas jamás prueba un cero."""

from datetime import date


def coverage_by_cell(entries, radios, weeks):
    """Expande intervalos completos de semanas sin inferir cobertura de los Excel."""
    result = {}
    radio_ids = set(radios)
    week_starts = {week.start for week in weeks}
    for entry in entries:
        start, end = date.fromisoformat(entry["start"]), date.fromisoformat(entry["end"])
        state, evidence = entry["state"], entry.get("evidence_ref")
        selected = set(entry.get("radio_ids", radios))
        if (start > end or start.weekday() != 6 or end.weekday() != 5
                or state not in {"complete", "partial", "outside"}
                or not isinstance(evidence, str) or not evidence.strip()
                or not selected or not selected <= radio_ids):
            raise ValueError("Cobertura sin evidencia o límites compatibles")
        for week_start in sorted(week_starts):
            if start <= week_start <= end:
                for radio in selected:
                    key = (radio, week_start)
                    if key in result:
                        raise ValueError("Declaraciones de cobertura superpuestas")
                    result[key] = (state, evidence)
    return result


def observation_state(count, pending, coverage, *, partial_window=False):
    """Un conteo positivo con cobertura desconocida es observado, pero incompleto."""
    if count < 0 or pending < 0 or coverage not in {"unknown", "complete", "partial", "outside"}:
        raise ValueError("Conteo o estado de cobertura inválidos")
    if coverage == "outside":
        if count or pending:
            raise ValueError("Registros contradicen una declaración fuera de cobertura")
        return None, "fuera_de_cobertura", "outside"
    if partial_window or coverage == "partial" or (coverage == "complete" and pending):
        return count if count else None, "cobertura_parcial", "partial"
    if count:
        return count, "registros_observados", coverage
    if coverage == "complete" and not pending:
        return 0, "cero_con_cobertura_comprobada", "complete"
    return None, "sin_informacion_suficiente", coverage
