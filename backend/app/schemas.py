import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PRIVACY_NOTICE_VERSION = "2026-08-19"


def clean_anonymous_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if re.search(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", cleaned):
        raise ValueError("No incluyas correos electrónicos: el reporte debe ser anónimo")
    if re.search(r"(?:\+?54[\s-]?)?(?:\d[\s-]?){9,}", cleaned):
        raise ValueError("No incluyas teléfonos ni DNI: el reporte debe ser anónimo")
    if re.search(r"\b\d{7,8}\b", cleaned):
        raise ValueError("No incluyas DNI: el reporte debe ser anónimo")
    return cleaned


class ReportCategory(str, Enum):
    standing_water = "agua_acumulada"
    bulky_waste = "neumaticos_chatarra"
    dumping = "microbasural"
    public_breeding_site = "criadero_espacio_publico"
    mosquitoes = "alta_presencia_mosquitos"
    vector_evaluation = "evaluacion_control_vectorial"
    other = "otro"


class ReportStatus(str, Enum):
    received = "recibido"
    reviewing = "en_revision"
    pending_referral = "pendiente_de_derivacion"
    referred = "derivado"
    resolved = "resuelto"
    discarded = "descartado"


class CitizenReportCreate(BaseModel):
    category: ReportCategory
    description: str = Field(min_length=20, max_length=600)
    latitude: float
    longitude: float
    address_reference: str | None = Field(default=None, max_length=200)
    neighborhood: str | None = Field(default=None, max_length=100)
    privacy_notice_version: str
    privacy_accepted: bool

    @field_validator("description", "address_reference", "neighborhood")
    @classmethod
    def reject_direct_contact_data(cls, value: str | None) -> str | None:
        return clean_anonymous_text(value)

    @model_validator(mode="after")
    def validate_privacy(self):
        if not self.privacy_accepted:
            raise ValueError("Debés aceptar el aviso de privacidad")
        if self.privacy_notice_version != PRIVACY_NOTICE_VERSION:
            raise ValueError("La versión del aviso de privacidad no es vigente")
        return self


class CitizenReportCreated(BaseModel):
    tracking_code: str
    status: ReportStatus
    created_at: datetime
    message: str


class AddressLookupRequest(BaseModel):
    address_reference: str = Field(min_length=4, max_length=200)

    @field_validator("address_reference")
    @classmethod
    def reject_direct_contact_data(cls, value: str) -> str:
        return clean_anonymous_text(value) or ""


class AddressLookupResponse(BaseModel):
    latitude: float
    longitude: float
    display_name: str


class PublicReportStatus(BaseModel):
    tracking_code: str
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
    public_status_message: str | None


class AdminLogin(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tracking_code: str
    category: str
    neighborhood: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class AdminReportDetail(AdminReportSummary):
    description: str
    latitude: float
    longitude: float
    address_reference: str | None
    public_status_message: str | None
    internal_notes: str | None
    possible_duplicate_of: str | None
    privacy_notice_version: str
    retention_until: datetime


class AdminReportPage(BaseModel):
    items: list[AdminReportSummary]
    total: int
    page: int
    page_size: int


class AdminReportUpdate(BaseModel):
    status: ReportStatus | None = None
    public_status_message: str | None = Field(default=None, max_length=600)
    internal_notes: str | None = Field(default=None, max_length=2000)
    possible_duplicate_of: str | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("No se informaron cambios")
        return self
