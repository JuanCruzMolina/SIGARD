"""Preflight diagnóstico de etapa 8, exclusivamente con entradas ficticias."""

from dataclasses import asdict, dataclass

import pandas as pd

from sigard_ml.official.epidemiological_validator import validate_label, validate_records, validate_week
from sigard_ml.official.epidemiological_validator.results import CheckResult as C, text
from sigard_ml.official.observed_dates import parse_reference_date
from sigard_ml.official.weekly_targets import validate_targets
from .evidence import ACCREDITED, EXPERIMENTAL, USES, SimulatedArtifact, dataset_digest, review_decision

VERSION = "epidemiological-preflight-0.8.0"
# Sólo reglas ya documentadas P1–P6 pueden recibir revisión explícita.
REVIEWABLE = {
    "classification.state": "P1", "episode.identity": "P2", "episode.resolution": "P2", "episode.accreditation": "P2",
    **{"date." + field: "P4" for field in ("symptom_onset", "consultation_on", "sample_on", "notified_on", "approximation", "chronology")},
    "spatial.uncertainty": "P5", "spatial.accreditation": "P5",
    **{"coverage." + name: "P3" for name in ("positive", "declared_zero", "accreditation", "unknown")},
    "label.positive": "P1", "label.inherited_zero": "P3", "label.experimental": "P3", "label.authorization": "P3",
}


@dataclass(frozen=True)
class Finding:
    group: str
    index: int
    result: C

    @property
    def key(self):
        return f"{self.group}:{self.index}:{self.result.control_id}:{self.result.status}:{self.result.field}"

    def to_dict(self):
        return {"key": self.key, **asdict(self)}


@dataclass(frozen=True)
class Eligibility:
    use: str
    status: str
    checks: tuple[C, ...]

    @property
    def blockers(self):
        return tuple(check for check in self.checks if check.status != "valido")


@dataclass(frozen=True)
class PreflightReport:
    dataset_sha256: str | None
    technical_checks: tuple[C, ...]
    findings: tuple[Finding, ...]
    eligibility: tuple[Eligibility, ...]

    @property
    def technical_consistent(self):
        return (not any(check.status == "invalido" for check in self.technical_checks)
                and not any(item.result.status == "invalido" for item in self.findings))

    @property
    def permitted_uses(self):
        return tuple("simulation_" + item.use for item in self.eligibility if not item.blockers)

    @property
    def training_authorized(self):
        return False

    @property
    def evaluation_authorized(self):
        return False

    def to_dict(self):
        return {"version": VERSION, "dataset_sha256": self.dataset_sha256,
                "technical_consistent": self.technical_consistent,
                "training_authorized": False, "evaluation_authorized": False,
                "permitted_uses": list(self.permitted_uses),
                "technical_checks": [asdict(check) for check in self.technical_checks],
                "passed_controls": [item.to_dict() for item in self.findings if item.result.status == "valido"],
                "warnings": [item.to_dict() for item in self.findings if item.result.status == "advertencia"],
                "pending_evidence": [item.to_dict() for item in self.findings if item.result.status == "pendiente_acreditacion"],
                "invalid_controls": [item.to_dict() for item in self.findings if item.result.status == "invalido"],
                "eligibility": [{"use": item.use, "status": item.status,
                                 "checks": [asdict(check) for check in item.checks],
                                 "blockers": [asdict(check) for check in item.blockers]} for item in self.eligibility]}


def _day(value):
    return parse_reference_date(value)[0]


def _bundle_checks(bundle):
    fields = {"data_kind", "dataset_id", "dataset_version", "records", "weeks", "labels"}
    if (not isinstance(bundle, dict) or set(bundle) != fields
            or not text(bundle.get("dataset_id")) or not text(bundle.get("dataset_version"))
            or any(not isinstance(bundle.get(group), list) or not bundle[group]
                   or not all(isinstance(row, dict) for row in bundle[group]) for group in ("records", "weeks", "labels"))):
        return [C("dataset.structure", "invalido", "Proveer identidad/versiones y listas no vacías de registros, semanas y objetivos.", "bundle")]
    return [C("dataset.structure", "valido", "Estructura del conjunto de prueba completa.", "bundle")]


def _alignment_checks(bundle):
    """Vínculos entre entradas; las validaciones de cada fila pertenecen a etapa 7."""
    weeks, labels = bundle["weeks"], bundle["labels"]
    cells = [(row.get("radio_censal"), _day(row.get("fecha_inicio_semana"))) for row in weeks]
    keys = [(row.get("radio_censal"), _day(row.get("fecha_inicio_semana"))) for row in labels]
    targets = [(row.get("radio_censal"), _day(row.get("fecha_inicio_semana_objetivo"))) for row in labels]
    if (any(not text(radio) or day is None for radio, day in cells + keys + targets)
            or len(set(cells)) != len(cells) or len(set(keys)) != len(keys)
            or not set(keys + targets) <= set(cells)):
        return [C("dataset.alignment", "invalido", "Claves semanales repetidas, incompletas o sin celda de origen/objetivo correspondiente.", "weeks,labels")]
    for row in bundle["records"]:
        if text(row.get("radio_candidate")) and row.get("week_start") is not None:
            if (row["radio_candidate"], _day(row["week_start"])) not in cells:
                return [C("dataset.alignment", "invalido", "Registro fuera del alcance semanal/territorial aportado.", "records")]
    by_cell = dict(zip(cells, weeks))
    for row, target in zip(labels, targets):
        cell = by_cell[target]
        observed, kind = cell.get("casos_observados"), row.get("tipo_etiqueta")
        expected = None if observed is None else int(observed > 0)
        if kind == "cero_asumido_experimental":
            coherent = (expected is None and row.get("pendientes_semana_objetivo") == cell.get("registros_pendientes_posibles")
                        and row.get("semana_objetivo_parcial") == cell.get("ventana_semanal_parcial"))
        else:
            coherent = row.get("objetivo_semana_siguiente") == expected
        if not coherent:
            return [C("dataset.target_link", "invalido", "La etiqueta o sus pendientes/parcialidad no corresponden a la celda objetivo aportada.", "labels,weeks")]
    frame = pd.DataFrame(labels).copy(deep=True)
    for name in ("fecha_inicio_semana", "fecha_inicio_semana_objetivo"):
        frame[name] = frame[name].map(_day)
    try:
        validate_targets(frame)
    except (ValueError, AttributeError, TypeError):
        return [C("dataset.horizon", "invalido", "El contrato de objetivos exactos t+1 no se cumple o intenta habilitar entrenamiento.", "labels")]
    return [C("dataset.alignment", "valido", "Claves enlazadas y horizonte exacto comprobado con validate_targets.", "weeks,labels")]


def _use_checks(bundle, findings, use, references, decision_ref):
    checks = []
    # No hay exclusiones automáticas: las filas desconocidas/ambiguas siguen en la entrada.
    hard_pending = {"date.reference", "episode.identity", "spatial.uncertainty", "classification.state", "label.unknown"}
    for item in findings:
        if item.result.status == "pendiente_acreditacion" and item.result.control_id in hard_pending:
            checks.append(C("eligibility.unresolved", "pendiente_acreditacion", "La entrada contiene clasificación, identidad, fecha, radio u objetivo sin resolver; no se elimina ni se imputa.", item.result.field))
    target_weeks = {(row["radio_censal"], _day(row["fecha_inicio_semana_objetivo"])): row for row in bundle["labels"]}
    for row in bundle["weeks"]:
        if row.get("casos_observados") is None:
            target = target_weeks.get((row["radio_censal"], _day(row["fecha_inicio_semana"])), {})
            assumed = (use == EXPERIMENTAL and target.get("tipo_etiqueta") == "cero_asumido_experimental")
            if not assumed:
                checks.append(C("eligibility.coverage", "pendiente_acreditacion", "Cobertura desconocida sin escenario experimental aplicable; no interpretar como negativo.", "casos_observados"))
        claims_verification = row.get("cobertura_comprobada") in ("complete", "partial")
        if ((use == ACCREDITED and row.get("cobertura_comprobada") != "complete")
                or (claims_verification and (not text(row.get("verificacion_cobertura_ref"))
                                            or row["verificacion_cobertura_ref"] != references.get("P3")))):
            checks.append(C("eligibility.coverage", "pendiente_acreditacion", "El uso acreditado requiere cobertura comprobada y vinculada al respaldo P3.", "verificacion_cobertura_ref"))
    for row in bundle["records"]:
        for flag, field, requirement in (("epidemiological_eligibility_validated", "classification_evidence_ref", "P1"),
                                         ("epidemiological_identity_validated", "identity_evidence_ref", "P2"),
                                         ("epidemiological_precision_validated", "spatial_evidence_ref", "P5")):
            required = use == ACCREDITED or row.get(flag) is True or (requirement == "P2" and row.get("identity_resolved_by_review") is True)
            if required and ((use == ACCREDITED and row.get(flag) is not True)
                             or not text(row.get(field)) or row[field] != references.get(requirement)):
                checks.append(C("eligibility." + requirement, "pendiente_acreditacion", "Acreditación declarada ausente o sin vínculo con el respaldo revisado de este uso.", field))
    for row in bundle["labels"]:
        if row.get("tipo_etiqueta") == "cero_asumido_experimental":
            if use == ACCREDITED:
                checks.append(C("eligibility.experimental_negative", "invalido", "Un negativo experimental no es una ausencia epidemiológica acreditada.", "tipo_etiqueta"))
            elif row.get("autorizacion_cobertura_ref") != decision_ref:
                checks.append(C("eligibility.experimental_scope", "pendiente_acreditacion", "La autorización del negativo debe resolver a la decisión experimental de esta huella.", "autorizacion_cobertura_ref"))
    return checks


def run_preflight(bundle, *, artifacts=None, decision_refs=None, requested_action="inspect"):
    """Sin IO ni entrenamiento. Las elegibilidades positivas son sólo simulaciones."""
    technical = _bundle_checks(bundle)
    findings, digest = [], None
    gates = []
    if not isinstance(bundle, dict) or bundle.get("data_kind") != "fictional":
        gates.append(C("execution.fictional_only", "invalido", "Esta etapa sólo admite conjuntos explícitamente ficticios; uso real bloqueado.", "data_kind"))
    if requested_action != "inspect":
        gates.append(C("execution.disabled", "invalido", "El preflight sólo inspecciona: entrenamiento y evaluación efectiva están deshabilitados.", "requested_action"))
    registry, refs = artifacts or {}, decision_refs or {}
    if not isinstance(registry, dict) or not isinstance(refs, dict) or set(refs) - set(USES):
        gates.append(C("decision.registry", "invalido", "Registro de evidencias o usos inválidos.", "decision_refs"))
        registry, refs = {}, {}
    if not any(check.status == "invalido" for check in technical) and bundle.get("data_kind") == "fictional":
        try:
            digest = dataset_digest(bundle)
            for group, groups in (("records", validate_records(bundle["records"])),
                                  ("weeks", [validate_week(row) for row in bundle["weeks"]]),
                                  ("labels", [validate_label(row) for row in bundle["labels"]])):
                findings.extend(Finding(group, index, check) for index, checks in enumerate(groups) for check in checks)
            # Evita reinterpretar entradas malformadas que ya rechazó el validador.
            if not any(item.result.status == "invalido" for item in findings):
                technical += _alignment_checks(bundle)
        except (ValueError, TypeError, OverflowError):
            technical.append(C("dataset.values", "invalido", "Valores de entrada no compatibles con el contrato JSON/fechas de etapa 7.", "bundle"))
    if gates and not findings:
        technical.append(C("validation.not_run", "invalido", "Validación de datos no ejecutada por restricciones de esta etapa.", "bundle"))
    technical_ok = not any(check.status == "invalido" for check in technical) and not any(item.result.status == "invalido" for item in findings)
    eligible = []
    review_findings = [item for item in findings if item.result.status in ("advertencia", "pendiente_acreditacion")]
    keys = {item.key for item in review_findings}
    for use in USES:
        checks = list(gates)
        if not technical_ok:
            checks.append(C("eligibility.technical", "invalido", "La consistencia técnica debe superarse antes de evaluar este uso.", "bundle"))
        else:
            evidence_checks, references, accepted = review_decision(registry, refs.get(use), use, digest, keys)
            checks += evidence_checks
            checks += _use_checks(bundle, findings, use, references, refs.get(use))
            for item in review_findings:
                if item.result.control_id not in REVIEWABLE or item.key not in accepted:
                    checks.append(C("eligibility.review", "pendiente_acreditacion", "Hallazgo del validador sin decisión explícita aplicable a este uso.", item.result.field))
        blocked = any(check.status != "valido" for check in checks)
        eligible.append(Eligibility(use, "blocked" if blocked else "eligible_simulation_only", tuple(checks)))
    return PreflightReport(digest, tuple(technical), tuple(findings), tuple(eligible))


__all__ = ["run_preflight", "dataset_digest", "SimulatedArtifact", "PreflightReport", "EXPERIMENTAL", "ACCREDITED"]
