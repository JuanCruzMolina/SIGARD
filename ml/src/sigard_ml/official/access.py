"""Contrato de autorización privada; no busca ni abre archivos."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from sigard_ml.official.contracts import require, require_text


class AuthorizedUse(str, Enum):
    INSPECTION = "inspection"
    PROCESSING = "processing"
    TRAINING = "training"
    EVALUATION = "evaluation"
    PUBLICATION = "publication"


class AccessDenied(PermissionError):
    """Denegación sin divulgar ruta, hoja, referencias ni registros."""


@dataclass(frozen=True)
class SourceAuthorization:
    """Una fuente externa completa o un extracto previamente autorizado.

    Nunca representa un filtro que obligue a abrir primero un libro mixto.
    Las referencias son opacas: su documentación permanece fuera de Git.
    """

    source_id: str
    source_version: str
    path: Path = field(repr=False)
    sheets: tuple[str, ...] = field(repr=False)
    subset_ref: str = field(repr=False)
    approved_extract: bool = False
    enabled: bool = False
    uses: frozenset[AuthorizedUse] = frozenset()
    evidence_ref: str | None = field(default=None, repr=False)
    custodian_ref: str | None = field(default=None, repr=False)
    confidentiality_ref: str | None = field(default=None, repr=False)
    storage_policy_ref: str | None = field(default=None, repr=False)
    all_sheets_approved: bool = False

    def __post_init__(self) -> None:
        for value in (self.source_id, self.source_version, self.subset_ref):
            require_text(value)
        require(isinstance(self.path, Path) and self.path.is_absolute(), "Se requiere ruta externa absoluta")
        require(type(self.sheets) is tuple and (bool(self.sheets) or self.all_sheets_approved), "Faltan hojas explícitas")
        for sheet in self.sheets:
            require_text(sheet)
            require(sheet != "*", "No se admite autorización global de hojas")
        require(len(self.sheets) == len(set(self.sheets)), "Hojas repetidas")
        require(type(self.uses) is frozenset and all(isinstance(use, AuthorizedUse) for use in self.uses),
                "Usos autorizados inválidos")
        require(type(self.enabled) is bool and type(self.approved_extract) is bool, "Flags de autorización inválidos")
        require(type(self.all_sheets_approved) is bool, "Alcance de libro inválido")

    def require_source_use(self, use: AuthorizedUse) -> None:
        """Permite inspeccionar estructura sólo con autorización del libro completo."""
        references = (self.evidence_ref, self.custodian_ref,
                      self.confidentiality_ref, self.storage_policy_ref)
        if not (self.enabled and self.approved_extract
                and isinstance(use, AuthorizedUse) and use in self.uses
                and all(isinstance(ref, str) and ref.strip() for ref in references)):
            raise AccessDenied("Acceso a fuente oficial no autorizado para el uso solicitado")

    def require_use(self, *, sheet: str, subset_ref: str, use: AuthorizedUse) -> None:
        """Precondición obligatoria antes de cualquier futura apertura del lector.

        No sustituye la aprobación científica B ni la aprobación pública C.
        Una instancia no prueba por sí sola la autenticidad de un permiso.
        """
        self.require_source_use(use)
        if not (subset_ref == self.subset_ref
                and (sheet in self.sheets or self.all_sheets_approved)):
            raise AccessDenied("Acceso a fuente oficial no autorizado para el alcance solicitado")


@dataclass(frozen=True)
class SourceRegistry:
    """Registro en memoria; vacío implica denegar todas las fuentes."""

    sources: tuple[SourceAuthorization, ...] = ()

    def __post_init__(self) -> None:
        require(type(self.sources) is tuple and all(isinstance(s, SourceAuthorization) for s in self.sources),
                "Registro de fuentes inválido")
        ids = [source.source_id for source in self.sources]
        require(len(ids) == len(set(ids)), "Fuente repetida en el registro")

    def authorize(self, source_id: str, *, sheet: str, subset_ref: str,
                  use: AuthorizedUse) -> SourceAuthorization:
        for source in self.sources:
            if source.source_id == source_id:
                source.require_use(sheet=sheet, subset_ref=subset_ref, use=use)
                return source
        raise AccessDenied("Fuente no habilitada en el registro privado")
