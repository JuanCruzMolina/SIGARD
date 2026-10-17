"""Cobertura declarada y comprobada separadas, sin inferir ausencia de filas."""

from datetime import date
from pathlib import Path
import re

from sigard_ml.official.coverage_settings import DATE_PANELS, VERIFIED_RULES
from sigard_ml.official.spatial_pipeline import digest_path


def validate_evidence(entry, repo_root):
    """Exige una resolución documentada; el hash verifica integridad, no verdad clínica."""
    if not isinstance(entry.get("verification_ref"), str) or not entry["verification_ref"].strip():
        raise ValueError("Falta resolución de verificación de cobertura")
    if entry.get("geographic_basis") != "patient_residence":
        raise ValueError("La cobertura territorial verificada debe distinguir residencia de notificación")
    rules = entry.get("rules_verified", {})
    if not isinstance(rules, dict) or any(rules.get(name) is not True for name in VERIFIED_RULES):
        raise ValueError("Faltan reglas verificadas para respaldar ceros conservadores")
    evidence_files = entry.get("evidence_files")
    if not isinstance(evidence_files, list) or not evidence_files or repo_root is None:
        raise ValueError("La cobertura comprobada requiere archivos privados de respaldo")
    for evidence in evidence_files:
        path = (repo_root / Path(evidence["path"])).resolve()
        private_roots = [(repo_root / name).resolve() for name in
                         ("data/interim/official", "data/processed/official", "data/datos oficiales")]
        if not any(path.is_relative_to(folder) for folder in private_roots):
            raise ValueError("El respaldo de cobertura debe estar en almacenamiento privado")
        if not re.fullmatch(r"[0-9a-f]{64}", evidence.get("sha256", "")) or digest_path(path) != evidence["sha256"]:
            raise ValueError("El respaldo de cobertura difiere de su huella")


def coverage_map(entries, radios, weeks, date_panel, *, verified=False, repo_root=None):
    """Un intervalo que sólo intersecta parte de una semana nunca la completa."""
    if date_panel not in DATE_PANELS:
        raise ValueError("Panel temporal desconocido")
    known_radios = set(radios)
    result = {}
    for entry in entries:
        start, end = date.fromisoformat(entry["start"]), date.fromisoformat(entry["end"])
        panels = entry.get("date_panels")
        state = entry["state"]
        selected = entry.get("radio_ids", list(radios))
        if (start > end or state not in {"complete", "partial", "unknown"}
            or not isinstance(panels, list) or not panels or len(panels) != len(set(panels))
            or not set(panels) <= set(DATE_PANELS) or not isinstance(selected, list)
            or not selected or len(selected) != len(set(selected)) or not set(selected) <= known_radios):
            raise ValueError("Período, estado, panel temporal o radios de cobertura inválidos")
        reference_name = "verification_ref" if verified else "declaration_ref"
        reference = entry.get(reference_name)
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("La cobertura requiere procedencia explícita")
        if verified:
            validate_evidence(entry, repo_root)
        if date_panel not in panels:
            continue
        for week in weeks:
            if end < week.start or start > week.end:
                continue
            effective = "partial" if state == "complete" and not (start <= week.start and week.end <= end) else state
            for radio in selected:
                key = radio, week.start
                if key in result:
                    raise ValueError("Intervalos de cobertura superpuestos requieren una decisión única por semana")
                result[key] = (effective, reference)
    return result


def decide_observation(count, pending, declared, verified, scenario, *, partial_window=False, zero_policy=None):
    if scenario not in {"conservative", "exploratory"} or count < 0 or pending < 0:
        raise ValueError("Escenario o conteos inválidos")
    if declared not in {"complete", "partial", "unknown"} or verified not in {"complete", "partial", "unknown"}:
        raise ValueError("Estado de cobertura desconocido")
    policy = zero_policy or {"enabled": True, "allow_declared_complete_in_exploratory": True}
    # La evidencia parcial de la fuente o de sus límites prevalece sobre una
    # declaración de completitud, aunque haya registros positivos observados.
    if partial_window or "partial" in (declared, verified):
        coverage, basis = "parcial", None
    elif verified == "complete":
        coverage, basis = "completa_comprobada", "verified"
    elif scenario == "exploratory" and declared == "complete" and policy["allow_declared_complete_in_exploratory"]:
        coverage, basis = "completa_declarada_provisional", "declared"
    else:
        coverage, basis = "desconocida", None
    if basis and pending:
        coverage, basis = "parcial_por_pendientes", None
    if count:
        return count, coverage, "positivo_provisional", False
    if basis and policy["enabled"]:
        return 0, coverage, "cero_comprobado_bajo_reglas" if basis == "verified" else "cero_declarado_provisional", basis == "declared"
    reason = "pendientes_pueden_modificar_conteo" if pending else (
        "periodo_parcial" if coverage == "parcial" else "sin_respaldo_para_cero")
    return None, coverage, reason, False
