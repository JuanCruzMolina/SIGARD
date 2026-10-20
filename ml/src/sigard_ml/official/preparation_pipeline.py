"""Entrada controlada de preparación en memoria, limitada a fixtures ficticias.

Reutiliza autorización de acceso, validador y preflight. No lee archivos, produce
matrices, escribe datasets ni ofrece una continuación hacia fit/evaluate.
"""

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass

from sigard_ml.official.access import AccessDenied, AuthorizedUse, SourceRegistry
from sigard_ml.official.epidemiological_preflight import ACCREDITED, PreflightReport, dataset_digest, run_preflight
from sigard_ml.official.epidemiological_preflight.evidence import USES
from sigard_ml.official.epidemiological_validator.results import CheckResult as C

VERSION = "controlled-epidemiological-preparation-0.9.0"
SECTIONS = ("records", "weeks", "labels")


def aggregate(checks):
    """Agrupa por control/estado/motivo/campo; no reproduce claves ni filas."""
    counts = Counter((check.control_id, check.status, check.reason, check.field) for check in checks)
    return [{**asdict(C(*key)), "count": count} for key, count in sorted(counts.items(), key=lambda item: repr(item[0]))]


@dataclass(frozen=True)
class PreparationResult:
    requested_use: str | None
    controls: tuple[C, ...]
    preflight: PreflightReport | None = None

    @property
    def selected_eligibility(self):
        if self.preflight is not None:
            return next(item for item in self.preflight.eligibility if item.use == self.requested_use)
        return None

    @property
    def blockers(self):
        checks = [check for check in self.controls if check.status != "valido"]
        if self.preflight is not None:
            checks += [check for check in self.preflight.technical_checks if check.status == "invalido"]
            checks += [item.result for item in self.preflight.findings if item.result.status == "invalido"]
            checks += list(self.selected_eligibility.blockers)
        return tuple(checks)

    @property
    def status(self):
        return "prepared_simulation_only" if self.preflight is not None and not self.blockers else "blocked"

    def to_dict(self):
        report = self.preflight
        findings = [item.result for item in report.findings] if report else []
        checks = list(self.controls)
        if report:
            checks += list(report.technical_checks) + list(self.selected_eligibility.checks)
        all_checks = checks + findings
        return {"version": VERSION, "status": self.status, "requested_use": self.requested_use,
                "dataset_sha256": report.dataset_sha256 if report else None,
                "validation_executed": report is not None and bool(report.findings),
                "preflight_executed": report is not None,
                "technical_consistent": report.technical_consistent if report else None,
                "permitted_uses": ["simulation_" + self.requested_use] if self.status == "prepared_simulation_only" else [],
                "training_enabled": False, "training_authorized": False, "evaluation_authorized": False,
                "datasets_written": False,
                "validation_counts": dict(Counter(check.status for check in findings)),
                "passed_controls": aggregate(check for check in all_checks if check.status == "valido"),
                "warnings": aggregate(check for check in all_checks if check.status == "advertencia"),
                "pending_evidence": aggregate(check for check in all_checks if check.status == "pendiente_acreditacion"),
                "blockers": aggregate(self.blockers)}


def run_preparation(bundle, *, registry=None, artifacts=None, decision_refs=None,
                    requested_use=ACCREDITED, operation=AuthorizedUse.PROCESSING):
    """Entrada -> autorización -> validador/preflight -> decisión -> informe.

    El registro lo aporta el contexto externo de pruebas. Autoriza un extracto
    ficticio identificado por dataset_id/source_version, sus tres secciones
    virtuales y subset_ref=SHA-256 del bundle exacto. Nunca se construye desde
    declaraciones del bundle ni habilita uso epidemiológico institucional.
    """
    controls = []
    selected = requested_use if requested_use in USES else None
    if selected is None:
        controls.append(C("preparation.use", "invalido", "Elegir uno de los usos de simulación existentes del preflight.", "requested_use"))
    if operation is not AuthorizedUse.PROCESSING:
        controls.append(C("preparation.operation", "invalido", "Sólo se admite preparación ficticia con informe; entrenamiento, evaluación y publicación están bloqueados.", "operation"))
    if not isinstance(bundle, dict) or bundle.get("data_kind") != "fictional":
        controls.append(C("preparation.fictional_only", "invalido", "Esta entrada sólo procesa fixtures declaradas ficticias y autorizadas por el contexto externo.", "data_kind"))
    if not isinstance(registry, SourceRegistry):
        controls.append(C("preparation.authorization", "invalido", "Falta el registro externo de autorización de procesamiento; el dataset no puede otorgarlo.", "registry"))
    if controls:
        return PreparationResult(selected, tuple(controls))
    # Trabaja sobre una instantánea: no modifica entradas ni permite cambiar el
    # contenido entre la comprobación de alcance y la decisión del preflight.
    try:
        snapshot = deepcopy(bundle)
        digest = dataset_digest(snapshot)
        for section in SECTIONS:
            source = registry.authorize(snapshot.get("dataset_id"), sheet=section, subset_ref=digest,
                                        use=AuthorizedUse.PROCESSING)
            if source.source_version != snapshot.get("dataset_version"):
                raise AccessDenied("Versión no autorizada")
    except (AccessDenied, ValueError, TypeError, OverflowError):
        return PreparationResult(selected, (C("preparation.authorization", "invalido",
            "Conjunto, versión, secciones o huella sin permiso externo de procesamiento aplicable.", "registry"),))
    controls.append(C("preparation.authorization", "valido", "Alcance ficticio autorizado en memoria; no acredita evidencia epidemiológica.", "registry"))
    # run_preflight ya invoca los validadores de etapa 7. No se admiten resultados
    # precalculados, omisiones ni una segunda implementación de esas validaciones.
    report = run_preflight(snapshot, artifacts=artifacts, decision_refs=decision_refs, requested_action="inspect")
    return PreparationResult(selected, tuple(controls), report)
