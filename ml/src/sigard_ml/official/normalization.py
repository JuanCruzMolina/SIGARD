"""Conversión conservadora de valores en memoria; nunca cambia las fuentes."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import math

from sigard_ml.official.excel import is_empty
from sigard_ml.official.settings import DATE_MAX_YEAR, DATE_MIN_YEAR

DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S")


def normalize_text(value) -> str | None:
    if is_empty(value):
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(int(value)) if float(value).is_integer() else str(value)
    return " ".join(str(value).strip().split())


def parse_date(value, formats=DATE_FORMATS) -> tuple[date | None, str]:
    """No interpreta números como fechas seriales ni adivina mes/día."""
    if normalize_text(value) is None:
        return None, "missing"
    if isinstance(value, datetime):
        parsed = value.date()
    elif type(value) is date:
        parsed = value
    elif isinstance(value, str):
        parsed = None
        for format_string in formats:
            try:
                parsed = datetime.strptime(value.strip(), format_string).date()
                break
            except ValueError:
                continue
        if parsed is None:
            return None, "invalid_format"
    else:
        return None, "invalid_format"
    if not DATE_MIN_YEAR <= parsed.year <= DATE_MAX_YEAR:
        return None, "out_of_range"
    return parsed, "valid"


def parse_coordinate(value) -> tuple[float | None, str, int | None]:
    text = normalize_text(value)
    if text is None:
        return None, "missing", None
    if isinstance(value, bool):
        return None, "invalid_format", None
    # Coma decimal simple; no separadores de miles, pares ni texto direccional.
    text = text.replace(",", ".")
    try:
        decimal = Decimal(text)
        number = float(decimal)
    except (InvalidOperation, ValueError, OverflowError):
        return None, "invalid_format", None
    if not math.isfinite(number):
        return None, "invalid_format", None
    places = max(0, -decimal.as_tuple().exponent)
    return number, "parsed", places
