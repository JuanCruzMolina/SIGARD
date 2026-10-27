"""Salida privada en memoria para el único horizonte autorizado de código: t+1."""

from datetime import date, timedelta

from sigard_ml.forecasting import VERSION
from sigard_ml.forecasting.contracts import ForecastError, day, require, week
from sigard_ml.forecasting.dataset import FEATURES, build_dataset
from sigard_ml.forecasting.training import predict
from sigard_ml.official.calendar_rules import CALENDAR_VERSION, DEFAULT_CALENDAR, CalendarError


def _query_date(value):
    """Entrada manual canónica; sin formatos ambiguos, horas ni coerciones."""
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise ForecastError("Fecha inválida; use YYYY-MM-DD") from error
        require(parsed.isoformat() == value, "Fecha inválida; use YYYY-MM-DD")
        return parsed
    return day(value)


def resolve_date_query(target_date, *, as_of, information_cutoff, horizon_weeks=1):
    """Plan sin inferencia, sin IO ni acreditación automática de disponibilidad.

    information_cutoff es el último cierre de información respaldado por el
    custodio. En backtesting se recorta al sábado anterior al objetivo; nunca
    se usa el corte actual para construir features históricas. Los snapshots
    y permisos del adaptador siguen siendo necesarios, también para ese corte.
    """
    target_date = _query_date(target_date)
    require(type(horizon_weeks) is int and horizon_weeks in (1, 2, 4), "Horizonte no soportado")
    day(as_of)
    day(information_cutoff)
    require(information_cutoff <= as_of, "El corte de información es posterior a la consulta")
    try:
        year, number = DEFAULT_CALENDAR.date_week(target_date)
        target, target_end = DEFAULT_CALENDAR.week_bounds(year, number)
        cutoff_year, cutoff_number = DEFAULT_CALENDAR.date_week(information_cutoff)
        _, cutoff_end = DEFAULT_CALENDAR.week_bounds(cutoff_year, cutoff_number)
        require(information_cutoff == cutoff_end, "El corte debe ser un sábado al cierre de una semana completa")
        origin = target - timedelta(weeks=horizon_weeks)
        required_cutoff = origin + timedelta(days=6)
        week(origin)
    except CalendarError as error:
        raise ForecastError("Fecha u origen fuera del calendario epidemiológico argentino verificado") from error
    require(required_cutoff <= information_cutoff,
            "Fecha no pronosticable: t+1 sólo admite la semana siguiente al corte; horizontes lejanos requieren otro modelo")
    return {"requested_date": target_date.isoformat(), "generated_as_of": as_of.isoformat(),
            "query_mode": "historical_backtest" if target_end <= as_of else "forecast",
            "latest_information_cutoff": information_cutoff.isoformat(),
            "information_cutoff": required_cutoff.isoformat(), "origin_week": origin.isoformat(),
            "target_week": target.isoformat(), "target_end": target_end.isoformat(),
            "target_year": year, "target_week_number": number,
            "calendar_version": CALENDAR_VERSION, "horizon_weeks": horizon_weeks}


def forecast_for_date(fitted, inputs, *, target_date, as_of, information_cutoff):
    """Consulta una fecha de la semana objetivo mediante el pronosticador t+1.

    No ajusta modelos ni encadena predicciones. La habilitación real conserva
    su bloqueo independiente; un plan de fecha válido no habilita inferencia.
    """
    query = resolve_date_query(target_date, as_of=as_of, information_cutoff=information_cutoff)
    require(fitted is not None, "Fecha no pronosticable: no hay modelo habilitado para conteos t+1")
    require(type(getattr(fitted, "horizon_weeks", None)) is int and fitted.horizon_weeks == 1,
            "Modelo no habilitado para el horizonte t+1; multihorizonte requiere otro contrato")
    result = forecast_next_week(fitted, inputs, as_of=date.fromisoformat(query["information_cutoff"]))
    require(result["status"] == "available_simulation_only",
            "Fecha no pronosticable: faltan conteos recientes completos y maduros al corte solicitado")
    result.update(query)
    return result


def forecast_next_week(fitted, inputs, *, as_of):
    """No retrocede a un origen obsoleto si falta historia del último corte.

    as_of se declara explícitamente; no ofrece fechas objetivo arbitrarias.
    Exige conteos completos/maduros en t-1 en todos los radios. Otros faltantes
    permanecen visibles y los transforma el pipeline ajustado en desarrollo.
    """
    inputs.validate()
    require(inputs.data_kind == "fictional", "Inferencia real deshabilitada: requiere autorización independiente")
    day(as_of)
    require(fitted is not None, "No hay modelo habilitado para conteos t+1")
    require(type(getattr(fitted, "horizon_weeks", None)) is int and fitted.horizon_weeks == 1,
            "Modelo no habilitado para el horizonte t+1")
    require(fitted.data_kind == "fictional", "Modelo real bloqueado")
    require(fitted.radios == inputs.radios and fitted.dataset_version == inputs.dataset_version, "Universo o versión incompatible con el modelo")
    year, number = DEFAULT_CALENDAR.date_week(as_of)
    origin, end = DEFAULT_CALENDAR.week_bounds(year, number)
    if as_of < end:
        origin -= timedelta(weeks=1)
    week(origin)
    cutoff = origin + timedelta(days=6)
    require(fitted.fit_cutoff <= cutoff, "El modelo fue ajustado después del origen solicitado")
    frame = build_dataset(inputs, start=origin, end=origin, evaluation_as_of=cutoff, include_outcomes=False)
    available = bool(frame.cases_lag_1.notna().all())
    metadata = {"schema_version": VERSION, "data_kind": "fictional", "real_forecast": False,
                "status": "available_simulation_only" if available else "blocked_missing_recent_counts",
                "model_id": fitted.model_id, "model_family": fitted.selected,
                "model_fit_cutoff": fitted.fit_cutoff.isoformat(), "dataset_version": inputs.dataset_version,
                "target_unit": inputs.count_unit,
                "seed": fitted.seed, "calendar_version": CALENDAR_VERSION, "horizon_weeks": 1,
                "generated_as_of": as_of.isoformat(), "information_cutoff": cutoff.isoformat(),
                "origin_week": origin.isoformat(), "target_week": frame.target_week.iloc[0].isoformat(),
                "target_end": frame.target_end.iloc[0].isoformat(), "target_year": int(frame.target_year.iloc[0]),
                "target_week_number": int(frame.target_week_number.iloc[0]),
                "epidemiological_history_through": (origin - timedelta(weeks=1)).isoformat(),
                "expected_capital_count": None, "radios": [],
                "probability_status": "not_accredited_no_calibration",
                "uncertainty": {"interval": None, "status": "unavailable_no_validated_method"}}
    predictions = predict(fitted.model, frame) if available else [None] * len(frame)
    for (_, row), value in zip(frame.iterrows(), predictions):
        metadata["radios"].append({"radio_id": row.radio_id,
            "expected_count": float(value) if value is not None else None,
            "presence_probability": None, "prediction_interval": None,
            "available_features": sum(bool(row[feature + "_available"]) for feature in FEATURES),
            "missing_features": [feature for feature in FEATURES if not row[feature + "_available"]],
            "provenance": row.provenance})
    if available:
        metadata["radios"].sort(key=lambda row: (-row["expected_count"], row["radio_id"]))
        last, rank = None, 0
        for row in metadata["radios"]:
            if row["expected_count"] != last:
                rank += 1
                last = row["expected_count"]
            row["concentration_rank"] = rank
        # Suma de esperanzas sin redondeos independientes ni ajuste oculto.
        metadata["expected_capital_count"] = sum(row["expected_count"] for row in metadata["radios"])
    return metadata
