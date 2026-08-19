from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SIGARD API"
    database_url: str = "sqlite:///./sigard_local.db"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    auto_create_schema: bool = False
    admin_bootstrap_email: str | None = None
    admin_bootstrap_password: str | None = None
    report_retention_days: int = 180
    report_rate_limit: int = 5
    geocoding_rate_limit: int = 10
    admin_login_rate_limit: int = 5
    municipal_receiver_confirmed: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if len(value) < 32 or value in {"development-only-change-me", "cambia_esto_por_una_clave_segura"}:
            raise ValueError("SECRET_KEY debe ser aleatoria, privada y tener al menos 32 caracteres")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
