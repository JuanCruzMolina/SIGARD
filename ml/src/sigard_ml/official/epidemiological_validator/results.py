"""Resultados técnicos; ninguno constituye una autorización epidemiológica."""

from dataclasses import asdict, dataclass
from typing import Literal

Status = Literal["valido", "advertencia", "invalido", "pendiente_acreditacion"]
VERSION = "epidemiological-validator-0.7.0"


@dataclass(frozen=True)
class CheckResult:
    control_id: str
    status: Status
    reason: str
    field: str | None = None

    def to_dict(self):
        return asdict(self)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def count(value):
    return type(value) is int and value >= 0
