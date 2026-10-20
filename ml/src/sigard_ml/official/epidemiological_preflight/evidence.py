"""Respaldos simulados en memoria. Integridad verificable no equivale a veracidad."""

from dataclasses import dataclass
from datetime import date
import hashlib
import json

from sigard_ml.official.epidemiological_validator.results import CheckResult as C, VERSION as VALIDATOR_VERSION, text
from sigard_ml.official.observed_dates import parse_reference_date

EXPERIMENTAL = "retrospective_experimental"
ACCREDITED = "epidemiological_accredited"
USES = (EXPERIMENTAL, ACCREDITED)
REQUIREMENTS = ("P1", "P2", "P3", "P4", "P5", "P6")


def canonical_bytes(value):
    def encode(item):
        if type(item) is date:
            return item.isoformat()
        raise TypeError("Se requieren valores JSON o fechas sin hora")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False, default=encode).encode("utf-8")


def dataset_digest(bundle):
    """Vincula versiones, filas, fechas, territorio, etiquetas y su orden exacto."""
    return hashlib.sha256(canonical_bytes(bundle)).hexdigest()


@dataclass(frozen=True)
class SimulatedArtifact:
    content: bytes
    sha256: str


def read_artifact(registry, reference):
    """Nunca interpreta una referencia como ruta o URL."""
    if not text(reference) or reference not in registry:
        raise ValueError("Referencia no resuelta")
    artifact = registry[reference]
    if (not isinstance(artifact, SimulatedArtifact) or type(artifact.content) is not bytes
            or hashlib.sha256(artifact.content).hexdigest() != artifact.sha256):
        raise ValueError("Respaldo ausente o con integridad inválida")
    document = json.loads(artifact.content)
    if not isinstance(document, dict) or document.get("simulation") is not True or document.get("reference") != reference:
        raise ValueError("El respaldo debe ser simulado y conservar su referencia")
    return document


def review_decision(registry, reference, use, digest, finding_keys):
    """Comprueba decisiones aportadas, sin redactar, aprobar ni autenticar firmas."""
    checks, references, accepted = [], {}, set()
    try:
        decision = read_artifact(registry, reference)
        if (decision.get("status") != "approved" or decision.get("use") != use
                or decision.get("dataset_sha256") != digest
                or decision.get("validator_version") != VALIDATOR_VERSION
                or not text(decision.get("reviewer_ref")) or not text(decision.get("rule_version"))
                or parse_reference_date(decision.get("decided_on"))[1] != "valid"):
            raise ValueError("Decisión no aprobada o fuera de alcance")
        references = decision.get("evidence_refs")
        items = decision.get("accepted_findings")
        if (not isinstance(references, dict) or set(references) != set(REQUIREMENTS)
                or not isinstance(items, list) or not all(text(item) for item in items)
                or len(set(items)) != len(items) or not set(items) <= finding_keys):
            raise ValueError("Decisión incompleta o hallazgos ajenos")
        accepted = set(items)
        checks.append(C("decision.scope", "valido", "Decisión simulada aprobada para esta huella, uso y versión del validador.", "decision_refs"))
    except (ValueError, TypeError, UnicodeError):
        return [C("decision.scope", "pendiente_acreditacion", "Falta decisión simulada íntegra, aprobada y aplicable al conjunto y uso exactos.", "decision_refs")], {}, set()
    for requirement in REQUIREMENTS:
        try:
            evidence = read_artifact(registry, references[requirement])
            if (evidence.get("requirement") != requirement or evidence.get("dataset_sha256") != digest
                    or not isinstance(evidence.get("uses"), list) or use not in evidence["uses"]
                    or evidence.get("review_state") != "reviewed" or not text(evidence.get("reviewer_ref"))
                    or not text(evidence.get("basis"))):
                raise ValueError("Respaldo insuficiente o fuera de alcance")
            checks.append(C("evidence." + requirement, "valido", "Respaldo simulado íntegro y revisado, vinculado al requisito y al conjunto exacto.", requirement))
        except (ValueError, TypeError, UnicodeError):
            checks.append(C("evidence." + requirement, "pendiente_acreditacion", "Falta respaldo simulado verificable, revisado y aplicable a este requisito y uso.", requirement))
    return checks, references, accepted
