"""Reglas inmutables del calendario, sin pandas, contratos ni acceso a archivos."""

from dataclasses import dataclass
from datetime import date, timedelta


CALENDAR_VERSION = "ar-snvs-2020-2026-v1"
LEGACY_VERSION = "sigard-iso-shift-v0"


class CalendarError(ValueError):
    """Fecha, semana o configuración fuera del calendario declarado."""


@dataclass(frozen=True)
class CalendarYear:
    year: int
    start: date
    weeks: int
    evidence: str

    def __post_init__(self):
        if (type(self.year) is not int or not 1 < self.year < 9999
                or type(self.start) is not date or self.start.weekday() != 6
                or not date(self.year - 1, 12, 26) <= self.start <= date(self.year, 1, 7)
                or type(self.weeks) is not int or self.weeks not in (52, 53)
                or not isinstance(self.evidence, str) or not self.evidence.strip()):
            raise CalendarError("Año de calendario inválido o sin evidencia")


@dataclass(frozen=True)
class Calendar:
    version: str
    years: tuple[CalendarYear, ...] = ()

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip() or type(self.years) is not tuple:
            raise CalendarError("Falta una versión inmutable de calendario")
        if self.version == LEGACY_VERSION:
            if self.years:
                raise CalendarError("El calendario histórico no admite redefiniciones")
            return
        if not self.years or not all(isinstance(entry, CalendarYear) for entry in self.years):
            raise CalendarError("Faltan años verificados")
        for previous, current in zip(self.years, self.years[1:]):
            if (current.year != previous.year + 1
                    or current.start != previous.start + timedelta(weeks=previous.weeks)):
                raise CalendarError("Años discontinuos, superpuestos o desordenados")
        if self.version == CALENDAR_VERSION and self.years != VERIFIED_YEARS:
            raise CalendarError("Cambiar reglas exige una nueva versión de calendario")

    def week_bounds(self, year: int, number: int) -> tuple[date, date]:
        if type(year) is not int or type(number) is not int or not 1 <= number <= 53:
            raise CalendarError("Año o semana epidemiológica inválidos")
        if self.version == LEGACY_VERSION:
            if not 1678 <= year <= 2260:
                raise CalendarError("Año fuera del rango histórico del adaptador")
            try:
                start = date.fromisocalendar(year, number, 1) - timedelta(days=1)
            except ValueError as error:
                raise CalendarError("Semana inexistente en el año declarado") from error
        else:
            entry = next((entry for entry in self.years if entry.year == year), None)
            if entry is None or number > entry.weeks:
                raise CalendarError("Año sin verificar o semana inexistente")
            start = entry.start + timedelta(weeks=number - 1)
        return start, start + timedelta(days=6)

    def date_week(self, value: date) -> tuple[int, int]:
        if type(value) is not date:
            raise CalendarError("Se requiere una fecha sin hora")
        if self.version == LEGACY_VERSION:
            shifted = (value + timedelta(days=1)).isocalendar()
            self.week_bounds(shifted.year, shifted.week)
            return shifted.year, shifted.week
        for entry in self.years:
            if entry.start <= value < entry.start + timedelta(weeks=entry.weeks):
                return entry.year, (value - entry.start).days // 7 + 1
        raise CalendarError("Fecha fuera de los años verificados; ampliar la configuración con evidencia")


# Los enlaces y las contradicciones se documentan en docs/official-calendar.md.
VERIFIED_YEARS = (
    CalendarYear(2020, date(2019, 12, 29), 53, "MSAL calendario 2020; calendario 2021"),
    CalendarYear(2021, date(2021, 1, 3), 52, "MSAL calendario 2021; calendario 2022"),
    CalendarYear(2022, date(2022, 1, 2), 52, "MSAL calendario 2022; calendario 2023"),
    CalendarYear(2023, date(2023, 1, 1), 52, "MSAL calendario 2023; BEN 635"),
    CalendarYear(2024, date(2023, 12, 31), 52, "MSAL calendario 2024; BEN 686"),
    CalendarYear(2025, date(2024, 12, 29), 53, "MSAL calendario 2025 inicio; calendario 2026 y BEN 790 cierre"),
    CalendarYear(2026, date(2026, 1, 4), 52, "MSAL calendario 2026; BEN 791"),
)
DEFAULT_CALENDAR = Calendar(CALENDAR_VERSION, VERIFIED_YEARS)
LEGACY_CALENDAR = Calendar(LEGACY_VERSION)


def calendar_from_config(config: dict) -> Calendar:
    """Selecciona una versión o construye otra con años explícitos y evidencia.

    No cambia el calendario global ni el período/cobertura de ningún panel.
    """
    if not isinstance(config, dict) or set(config) - {"version", "years"}:
        raise CalendarError("Configuración de calendario inválida")
    version = config.get("version")
    if version == LEGACY_VERSION and "years" in config:
        raise CalendarError("El calendario histórico no admite redefiniciones")
    if "years" not in config:
        if version == CALENDAR_VERSION:
            return DEFAULT_CALENDAR
        if version == LEGACY_VERSION:
            return LEGACY_CALENDAR
        raise CalendarError("Versión desconocida sin años explícitos")
    try:
        entries = tuple(CalendarYear(row["year"], date.fromisoformat(row["start"]),
                                     row["weeks"], row["evidence"]) for row in config["years"])
        return Calendar(version, entries)
    except (KeyError, TypeError, ValueError) as error:
        raise CalendarError("Configuración de calendario inválida") from error
