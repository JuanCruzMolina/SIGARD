"""Calendario argentino verificado y reproducción explícita de la regla anterior."""

from datetime import date, timedelta

from sigard_ml.official.calendar_rules import Calendar, CalendarError, DEFAULT_CALENDAR
from sigard_ml.official.contracts import ContractError, EpidemiologicalWeek, require


def make_week(year: int, number: int, *, calendar: Calendar = DEFAULT_CALENDAR) -> EpidemiologicalWeek:
    """Intervalo domingo-sábado; rechaza años no verificados y SE53 inexistentes."""
    require(isinstance(calendar, Calendar), "Configuración de calendario inválida")
    try:
        start, end = calendar.week_bounds(year, number)
    except CalendarError as error:
        raise ContractError(str(error)) from error
    return EpidemiologicalWeek(year, number, start, end, calendar=calendar)


def week_from_date(value: date, *, calendar: Calendar = DEFAULT_CALENDAR) -> EpidemiologicalWeek:
    """Obtiene año-SE sin deducirlo del nombre del archivo ni del año civil."""
    require(isinstance(calendar, Calendar), "Configuración de calendario inválida")
    try:
        year, number = calendar.date_week(value)
    except CalendarError as error:
        raise ContractError(str(error)) from error
    return make_week(year, number, calendar=calendar)


def weeks_between(start: date, end: date, *, calendar: Calendar = DEFAULT_CALENDAR):
    """Semanas completas que intersectan el período; no presume cobertura."""
    require(type(start) is date and type(end) is date and start <= end, "Período inválido")
    current, last = week_from_date(start, calendar=calendar), week_from_date(end, calendar=calendar)
    result = []
    while current.start <= last.start:
        result.append(current)
        if current.start == last.start:
            break
        current = week_from_date(current.start + timedelta(days=7), calendar=calendar)
    return result
