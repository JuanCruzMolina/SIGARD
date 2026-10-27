"""Entrada privada de agregados derivados; sin originales, modelos ni entrenamiento.

El registro de permisos y los documentos revisados son una frontera de confianza
humana. SHA-256 comprueba integridad/alcance, nunca autenticidad institucional.
Las referencias opacas no se interpretan como rutas o URLs.
"""

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pandas as pd

from sigard_ml.forecasting.contracts import (
    Inputs, ForecastError, PROVISIONAL_EXPERIMENT, day, experimental, require, week,
)
from sigard_ml.official.access import AuthorizedUse, SourceRegistry
from sigard_ml.official.calendar_rules import CALENDAR_VERSION, DEFAULT_CALENDAR
from sigard_ml.official.epidemiological_preflight.evidence import REQUIREMENTS, canonical_bytes
from sigard_ml.official.episodes import PRINCIPAL_EPISODE_POLICY, validate_episode_summary

SCHEMA = "principal-count-input-1"
PROVISIONAL_SCHEMA = "principal-provisional-input-1"
SNAPSHOT_SCHEMA = "principal-snapshot-input-2"
KINDS = {"fictional", "epidemiological_accredited"}
UNIT = "eligible_episode_count"
VARIABLES = {
    "counts": ("count", "state", "coverage_complete", "pending", "mature"),
    "climate": ("temperature", "humidity", "precipitation", "complete"),
    "territory": ("population", "area_km2"),
    "graph": ("edges",),
}
TABLE_COLUMNS = {
    "counts": {"radio_id", "week_start", "available_on", "count", "state", "coverage_complete",
               "pending", "mature", "source_ref", "label_kind", "partial_week"},
    "climate": {"week_start", "available_on", "temperature", "humidity", "precipitation",
                "complete", "source_ref", "partial_week"},
    "territory": {"radio_id", "available_on", "population", "area_km2", "source_ref"},
}


def territorial_components(config, root, *, available_on, source_ref,
                           graph_available_on, graph_ref):
    """Prepara sólo contexto del principal; fechas P6 explícitas, sin conteos.

    La configuración aprobada fija la versión. Esta conversión no acredita P5/P6
    ni crea un paquete elegible: adapt_derived sigue exigiendo todas las decisiones.
    No asigna ni filtra registros epidemiológicos.
    """
    from sigard_ml.territorial.universe import graph_edges, load_version

    day(available_on)
    day(graph_available_on)
    require(_text(source_ref) and _text(graph_ref), "Falta procedencia territorial/vecinal")
    frame = load_version(config, root)
    territory = pd.DataFrame(frame[["radio_id", "poblacion", "superficie_km2"]]).rename(
        columns={"poblacion": "population", "superficie_km2": "area_km2"})
    territory["available_on"] = available_on
    territory["source_ref"] = source_ref
    return dict(territory_version=config["territory_version"], radios=tuple(frame.radio_id),
                territory=territory,
                graph=dict(edges=[list(edge) for edge in graph_edges(frame)],
                           available_on=graph_available_on, source_ref=graph_ref))


def climate_snapshots(weekly, *, availability, source_ref):
    """Mapea clima oficial al contrato existente, sin IO ni autorización de uso.

    availability: dict date->date aportado con evidencia P6, nunca inferido del
    cierre semanal o de una extracción SISA. La validación documental continúa
    en adapt_derived. Mínimas/máximas se conservan en el derivado semanal; el
    contrato principal actual consume media, humedad y precipitación.
    """
    columns = {"epidemiological_year", "epidemiological_week", "week_start_date",
               "week_end_date", "calendar_version", "temperature_mean",
               "relative_humidity_mean", "precipitation_sum", "climate_days_observed",
               "climate_week_complete", "climate_values_complete"}
    require(isinstance(weekly, pd.DataFrame) and columns <= set(weekly.columns)
            and not weekly.empty, "Falta clima semanal oficial")
    require(_text(source_ref) and isinstance(availability, dict), "Falta procedencia o disponibilidad climática explícita")
    require(weekly.calendar_version.eq(CALENDAR_VERSION).all(), "Calendario climático incompatible")
    require(not weekly.week_start_date.duplicated().any(), "Semana climática duplicada")
    starts = set(weekly.week_start_date.dt.date)
    require(set(availability) == starts, "Disponibilidad debe cubrir exactamente las semanas seleccionadas")
    records = []
    for row in weekly.itertuples():
        start, end = row.week_start_date.date(), row.week_end_date.date()
        year, number = week(start)
        require(row.week_start_date == pd.Timestamp(start) and row.week_end_date == pd.Timestamp(end)
                and (year, number) == (row.epidemiological_year, row.epidemiological_week)
                and DEFAULT_CALENDAR.week_bounds(year, number) == (start, end), "Fechas climáticas desalineadas")
        require(row.climate_days_observed == 7 and type(row.climate_week_complete) is bool
                and row.climate_week_complete and type(row.climate_values_complete) is bool
                and row.climate_values_complete, "Clima semanal incompleto")
        available = day(availability[start])
        require(available >= end, "Clima disponible antes del cierre semanal")
        records.append(dict(week_start=start, available_on=available,
                            temperature=row.temperature_mean, humidity=row.relative_humidity_mean,
                            precipitation=row.precipitation_sum, complete=True,
                            source_ref=source_ref, partial_week=False))
    result = pd.DataFrame(records)
    for field in ("temperature", "humidity", "precipitation"):
        require(result[field].notna().all() and result[field].map(
            lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)
            and float('-inf') < value < float('inf')).all(), "Clima debe ser numérico completo y finito")
    require(result.humidity.between(0, 100).all() and result.precipitation.ge(0).all(), "Clima fuera de rango")
    return result


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _date(value):
    require(isinstance(value, str), "Fecha debe ser ISO YYYY-MM-DD")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ForecastError("Fecha ISO inválida") from error
    require(result.isoformat() == value, "Fecha debe ser ISO YYYY-MM-DD")
    return result


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _json(content, limit):
    require(type(content) is bytes and len(content) <= limit, "Documento ausente o demasiado grande")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Clave JSON repetida")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ForecastError("JSON no finito")

    try:
        result = json.loads(content, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ForecastError("JSON inválido") from error
    require(isinstance(result, dict), "Se requiere objeto JSON")
    return result


@dataclass(frozen=True)
class EvidenceDocument:
    """Bytes aportados por el custodio con su huella esperada, fuera de Git."""

    content: bytes
    sha256: str


@dataclass(frozen=True)
class AdapterRequest:
    source_id: str
    source_version: str
    subset_ref: str
    package_sha256: str
    preparation_ref: str
    decision_ref: str
    review_as_of: date
    mode: str = "accredited_episode_preparation"


def _authorize(registry, request):
    require(isinstance(registry, SourceRegistry) and isinstance(request, AdapterRequest), "Falta registro o solicitud explícita")
    day(request.review_as_of)
    require(request.mode in {"accredited_episode_preparation", PROVISIONAL_EXPERIMENT}, "Modalidad desconocida")
    require(all(_text(getattr(request, field)) for field in
                ("source_id", "source_version", "subset_ref", "preparation_ref", "decision_ref")), "Solicitud incompleta")
    require(isinstance(request.package_sha256, str) and len(request.package_sha256) == 64
            and all(char in "0123456789abcdef" for char in request.package_sha256), "Falta SHA-256 exacto")
    source = registry.authorize(request.source_id, sheet="derived_bundle", subset_ref=request.subset_ref,
                                use=AuthorizedUse.PROCESSING)
    source.require_use(sheet="derived_bundle", subset_ref=request.subset_ref, use=AuthorizedUse.INSPECTION)
    if request.mode == PROVISIONAL_EXPERIMENT:
        for use in (AuthorizedUse.TRAINING, AuthorizedUse.EVALUATION):
            source.require_use(sheet="derived_bundle", subset_ref=request.subset_ref, use=use)
    require(source.source_version == request.source_version, "Versión fuera del permiso")
    return source


def load_derived(registry, request, *, documents):
    """Único lector: un JSON derivado autorizado, sin descubrir otras entradas.

    No abre originales ni documentos referenciados. La ruta resuelta debe estar
    bajo data/interim o data/processed del repositorio; enlaces de escape denegados.
    """
    source = _authorize(registry, request)
    path = source.path.resolve()
    root = Path(__file__).resolve().parents[4]
    require(path.suffix == ".json" and any(path.is_relative_to(root / "data" / folder)
            for folder in ("interim", "processed")), "Sólo JSON derivado dentro de data/interim o data/processed")
    require(path.stat().st_size <= 32 * 1024 * 1024, "Paquete demasiado grande")
    return adapt_derived(path.read_bytes(), registry, request, documents=documents)


def _document(documents, reference, request, kind, role):
    require(isinstance(documents, dict) and _text(reference), "Registro documental inválido")
    artifact = documents.get(reference)
    require(isinstance(artifact, EvidenceDocument) and type(artifact.content) is bytes
            and _sha(artifact.content) == artifact.sha256, "Evidencia ausente o integridad inválida")
    document = _json(artifact.content, 2 * 1024 * 1024)
    require(document.get("reference") == reference and document.get("role") == role
            and document.get("data_kind") == kind and document.get("package_sha256") == request.package_sha256
            and document.get("status") == "approved", "Evidencia no aprobada o ajena al paquete/condición/uso")
    require(all(_text(document.get(key)) for key in ("reviewer_ref", "basis", "rule_version", "limits")), "Evidencia sin responsable, respaldo, regla o límites")
    require(_date(document.get("decided_on")) <= request.review_as_of, "Decisión posterior al corte de revisión")
    return document


def _scope(bundle):
    return {key: bundle[key] for key in ("dataset_version", "calendar_version", "count_unit", "period_start", "period_end", "radios")}


def _fingerprint(inputs):
    """Detecta cambios posteriores en tablas, universo, grafo y metadatos."""
    value = {name: getattr(inputs, name) for name in
             ("radios", "edges", "graph_available_on", "graph_ref", "dataset_version", "data_kind", "count_unit", "input_evidence")}
    value["experiment_mode"] = getattr(inputs, "experiment_mode", None)
    # object evita que pandas reemplace None por NaN en columnas float.
    for name in TABLE_COLUMNS:
        frame = getattr(inputs, name).astype(object)
        value[name] = frame.where(pd.notna(frame), None).to_dict("records")
    return _sha(canonical_bytes(value))


class _DerivedInputs(Inputs):
    """Entrada verificada; sólo el modo experimental incorpora permiso de ajuste."""

    def validate(self):
        require(_fingerprint(self) == self._validated_sha256, "Entrada modificada después de su validación")
        self._recheck()
        self._validate_snapshots(lambda ref: ref in self._source_refs, retrospective=experimental(self))

    @property
    def training_authorized(self):
        # Permiso específico de ejecución, sin acreditar episodios ni producción.
        self.validate()
        return experimental(self)

    @property
    def evaluation_authorized(self):
        self.validate()
        return experimental(self)

    def validate_window(self, start, end, evaluation_as_of, *, include_outcomes=True, horizon_weeks=1):
        first, last, review = self._window
        required_end = end + timedelta(weeks=horizon_weeks) if include_outcomes else end
        require(start - timedelta(weeks=4) >= first and required_end <= last,
                f"Ventana fuera del período autorizado: requiere historia t−4 y objetivo t+{horizon_weeks}")
        require(evaluation_as_of <= review, "Congelamiento posterior al corte autorizado")


def adapt_derived(content, registry, request, *, documents):
    """Adapta bytes ya autorizados sin IO; no ajusta, evalúa ni infiere.

    El permiso se verifica antes de interpretar datos. Las decisiones del registro
    identifican su fundamento real: permiso externo o declaración expresa del
    responsable para agregados experimentales locales; no autentican instituciones.
    """
    try:
        return _adapt_derived(content, registry, request, documents=documents)
    except (TypeError, KeyError, AttributeError, OverflowError) as error:
        raise ForecastError("Estructura o valores incompatibles con el contrato derivado") from error


def _adapt_derived(content, registry, request, *, documents):
    source = _authorize(registry, request)
    require(type(content) is bytes and _sha(content) == request.package_sha256, "Integridad del paquete inválida")
    bundle = _json(content, 32 * 1024 * 1024)
    provisional = request.mode == PROVISIONAL_EXPERIMENT
    snapshot = provisional and bundle.get("schema_version") == SNAPSHOT_SCHEMA
    fields = {"schema_version", "data_kind", "dataset_version", "calendar_version", "count_unit",
              "period_start", "period_end", "radios", "sources", "counts", "climate", "territory", "graph"}
    if provisional:
        fields |= {"territory_version", "upstream_sources", "target_definition", "evaluation_mode"}
    if snapshot:
        fields.add("snapshot_scenario")
    require(set(bundle) == fields and bundle["schema_version"] == (SNAPSHOT_SCHEMA if snapshot else PROVISIONAL_SCHEMA if provisional else SCHEMA), "Esquema de paquete incompatible")
    kind = bundle["data_kind"]
    require((kind == ("epidemiological_snapshot_scenario" if snapshot else "epidemiological_provisional_records")
             and bundle["count_unit"] == ("snapshot_record_count" if snapshot else "provisional_record_count"))
            if provisional else (kind in KINDS and bundle["count_unit"] == UNIT),
            "Condición o unidad incompatible con la modalidad")
    require(bundle["dataset_version"] == request.source_version and bundle["calendar_version"] == CALENDAR_VERSION, "Versión o calendario incompatible")
    radios = bundle["radios"]
    require(isinstance(radios, list) and radios and all(_text(radio) for radio in radios)
            and len(set(radios)) == len(radios), "Universo vacío o duplicado")
    if kind == "fictional":
        require(all(radio.startswith("fictional_") for radio in radios), "Fixture debe tener radios ficticios")
    start, end = _date(bundle["period_start"]), _date(bundle["period_end"])
    week(start)
    week(end)
    require(start <= end and end + timedelta(days=6) <= request.review_as_of, "Período incompleto o invertido")
    expected_scope = _scope(bundle)
    if provisional:
        require(bundle["territory_version"] == "la-rioja-46014010-256-v1" and len(radios) == 256,
                "El experimento requiere el territorio operativo de 256 radios")
        require(bundle["target_definition"] == ("principal-confirmed-snapshot-2" if snapshot else "principal-confirmed-records-1")
                and bundle["evaluation_mode"] == "retrospective_event_time", "Objetivo o evaluación experimental incompatible")
        expected_scope.update({key: bundle[key] for key in
                               ("territory_version", "target_definition", "evaluation_mode", "upstream_sources")})
    if snapshot:
        policy = bundle["snapshot_scenario"]
        require(isinstance(policy, dict) and set(policy) == {"scenario_id", "covered_weeks", "zero_meaning",
                "quality_masks_sha256", "declaration_ref", "special_2022_policy"}, "Falta política explícita del snapshot")
        require(policy["scenario_id"] == "confirmed-snapshot-observed-weeks-2"
                and policy["zero_meaning"] == "no_record_in_filtered_snapshot_not_epidemiological_absence"
                and policy["special_2022_policy"] == "excluded_separate_not_confirmed_or_negative"
                and _text(policy["declaration_ref"])
                and isinstance(policy["quality_masks_sha256"], str) and len(policy["quality_masks_sha256"]) == 64
                and all(char in "0123456789abcdef" for char in policy["quality_masks_sha256"]),
                "Hipótesis o máscaras del snapshot incompatibles")
        covered = [_date(value) for value in policy["covered_weeks"]]
        require(covered and len(set(covered)) == len(covered)
                and all(start <= value <= end and week(value)[0] != 2022 for value in covered), "Cobertura del snapshot inválida")
        expected_scope["snapshot_scenario"] = policy
    reviewed_documents = {}

    def document(reference, role):
        result = _document(documents, reference, request, kind, role)
        require(result.get("scope") == expected_scope, "Evidencia fuera del período/universo/versiones")
        reviewed_documents[reference] = (role, result)
        return result

    preparation = document(request.preparation_ref, "provisional_experiment_preparation" if provisional else "count_preparation")
    require(source.evidence_ref == request.preparation_ref and preparation.get("source_id") == request.source_id
            and preparation.get("subset_ref") == request.subset_ref, "Permiso y preparación no coinciden")
    decision = document(request.decision_ref, "provisional_experiment_use" if provisional else "count_training_eligibility")
    refs, evidence = {}, {}
    if provisional:
        require(decision.get("experiment_mode") == PROVISIONAL_EXPERIMENT
                and decision.get("conditional_on_observed_cells") is (not snapshot)
                and decision.get("production_inference_authorized") is False
                and decision.get("historical_availability_accredited") is False,
                "Falta autorización de uso y aceptación de límites experimentales")
        if snapshot:
            require(decision.get("snapshot_zero_assumption_accepted") is True
                    and decision.get("local_retrospective_query_authorized") is True,
                    "Falta aceptación explícita del escenario y consulta privada")
        owner_declaration = decision.get("authorization_basis") == "project_owner_declared_provision"
        if owner_declaration:
            require(_text(decision.get("project_owner_declaration_ref"))
                    and decision.get("institutionally_signed") is False
                    and decision.get("local_experimental_only") is True
                    and not decision.get("provider_permission_ref"),
                    "Declaración del responsable sin alcance local o con atribución institucional incompatible")
        else:
            require(decision.get("authorization_basis") in (None, "external_provider_permission")
                    and _text(decision.get("provider_permission_ref"))
                    and not decision.get("project_owner_declaration_ref"),
                    "Falta fundamento explícito de autorización experimental")
        upstream = bundle["upstream_sources"]
        require(isinstance(upstream, list) and upstream, "Falta procedencia autorizada aguas arriba")
        lineage_versions = {}
        for item in upstream:
            require(isinstance(item, dict) and set(item) == {"source_id", "source_version", "sheet", "subset_ref"}
                    and all(_text(value) for value in item.values()), "Alcance de fuente incompleto")
            require(item["source_id"] not in lineage_versions, "Fuente aguas arriba duplicada")
            for use in (AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING, AuthorizedUse.TRAINING, AuthorizedUse.EVALUATION):
                permitted = registry.authorize(item["source_id"], sheet=item["sheet"], subset_ref=item["subset_ref"], use=use)
                require(permitted.source_version == item["source_version"], "Versión aguas arriba fuera de permiso")
            lineage_versions[item["source_id"]] = item["source_version"]
    else:
        refs = decision.get("evidence_refs")
        require(isinstance(refs, dict) and set(refs) == set(REQUIREMENTS)
                and all(_text(ref) for ref in refs.values()) and len(set(refs.values())) == 6, "Faltan decisiones P1–P6 separadas")
        evidence = {requirement: document(refs[requirement], requirement) for requirement in REQUIREMENTS}
    sources = bundle["sources"]
    require(isinstance(sources, dict) and set(sources) == set(VARIABLES), "Falta procedencia por componente")
    for component, metadata in sources.items():
        require(isinstance(metadata, dict) and set(metadata) == {"source_id", "source_version", "transformation_version", "provenance_ref"}
                and all(_text(value) for value in metadata.values()), "Procedencia/versionado incompleto")
        lineage = document(metadata["provenance_ref"], "provenance")
        require(lineage.get("component") == component and lineage.get("source") == metadata, "Procedencia no enlazada al componente exacto")
        if provisional:
            require(lineage_versions.get(metadata["source_id"]) == metadata["source_version"], "Componente sin permiso de uso aguas arriba")

    frames, inventory = {}, []
    for component, columns in TABLE_COLUMNS.items():
        rows = bundle[component]
        require(isinstance(rows, list) and rows and all(isinstance(row, dict) and set(row) == columns for row in rows), "Esquema agregado inválido; no admite campos personales ni coordenadas")
        frame = pd.DataFrame(rows)
        for column in ("week_start", "available_on"):
            if column in frame:
                frame[column] = frame[column].map(lambda value: None if provisional and column == "available_on" and value is None else _date(value))
        require(frame.source_ref.eq(sources[component]["provenance_ref"]).all(), "Referencia ajena a procedencia del componente")
        require(all(value is None or value <= request.review_as_of for value in frame.available_on), "Snapshot posterior al corte de revisión")
        if component != "territory":
            require(frame.partial_week.map(lambda value: type(value) is bool and not value).all(), "Período semanal parcial rechazado")
            require(frame.week_start.between(start, end).all(), "Semana fuera del alcance")
            frame = frame.drop(columns="partial_week")
        if component == "counts":
            kinds = {"complete": "accredited_episode_count", "provisional": "snapshot_record_count" if snapshot else "provisional_record_count", "unknown": "unknown"}
            for row in frame.itertuples():
                require(row.state in kinds and row.label_kind == kinds[row.state], "Etiqueta provisional/no acreditada incompatible con su estado")
                if provisional:
                    valid = ((row.state == "provisional" and pd.notna(row.count) and row.count >= 0 and row.pending is False)
                             or (row.state == "unknown" and pd.isna(row.count))) if snapshot else (
                                 row.state == "provisional" and pd.notna(row.count) and row.count > 0)
                    require(valid and row.coverage_complete is False and row.mature is False,
                            "Conteo experimental incompatible con máscaras/hipótesis; sin cobertura/madurez acreditada")
                if row.state == "complete":
                    require(row.coverage_complete is True and row.pending is False and row.mature is True
                            and pd.notna(row.count), "Etiqueta completa sin cobertura/madurez o con pendientes")
                elif row.state == "unknown":
                    require(pd.isna(row.count), "Desconocido debe conservar conteo null")
            frame = frame.drop(columns="label_kind")
        if component == "climate":
            require(frame.complete.map(lambda value: type(value) is bool and value).all()
                    and frame[["temperature", "humidity", "precipitation"]].notna().all().all(), "Clima semanal incompleto")
        keys = ["radio_id", "week_start"] if component == "counts" else ["week_start"] if component == "climate" else ["radio_id"]
        for row in frame.to_dict("records"):
            inventory.append({"component": component, "key": [row[key].isoformat() if type(row[key]) is date else row[key] for key in keys],
                              "available_on": row["available_on"].isoformat() if row["available_on"] else None,
                              "variables": list(VARIABLES[component])})
        frames[component] = frame

    if not provisional:
        _check_episode_counts(evidence["P2"], frames["counts"])
    weeks = [start + timedelta(weeks=index) for index in range((end - start).days // 7 + 1)]
    if not provisional:
        require(set(zip(frames["counts"].radio_id, frames["counts"].week_start)) == {(radio, value) for radio in radios for value in weeks}, "Grilla incompleta: faltan radios/semanas; no se rellenan ceros")
    if snapshot:
        require(set(zip(frames["counts"].radio_id, frames["counts"].week_start)) == {(radio, value) for radio in radios for value in covered},
                "La grilla snapshot debe preservar sus radios, semanas y desconocidos explícitos")
    require((set(frames["climate"].week_start) <= set(weeks) if provisional else set(frames["climate"].week_start) == set(weeks))
            and set(frames["territory"].radio_id) == set(radios), "Contexto incompleto o territorio incompatible")
    graph = bundle["graph"]
    require(isinstance(graph, dict) and set(graph) == {"edges", "available_on", "source_ref"}
            and graph["source_ref"] == sources["graph"]["provenance_ref"], "Grafo sin procedencia")
    graph_date = None if provisional and graph["available_on"] is None else _date(graph["available_on"])
    require((graph_date is None or graph_date <= request.review_as_of) and isinstance(graph["edges"], list)
            and all(isinstance(edge, list) and len(edge) == 2 and all(_text(radio) for radio in edge) for edge in graph["edges"]), "Grafo inválido")
    inventory.append({"component": "graph", "key": [], "available_on": graph_date.isoformat() if graph_date else None, "variables": ["edges"]})
    attestations = evidence["P6"].get("snapshots") if not provisional else []
    if provisional:
        inventory = []  # No se inventan atestaciones P6 para una exportación retrospectiva.
    require(isinstance(attestations, list) and len(attestations) == len(inventory), "P6 no acredita todos los snapshots y variables")
    attested = []
    for item in attestations:
        require(isinstance(item, dict) and set(item) == {"component", "key", "available_on", "variables", "observed_through", "basis_ref"}
                and _text(item["basis_ref"]), "P6 requiere respaldo de disponibilidad efectiva")
        through, available = _date(item["observed_through"]), _date(item["available_on"])
        require(through <= available, "Fuga temporal: observación posterior a disponibilidad")
        component = item["component"]
        require(component in VARIABLES, "Variable ajena a P6")
        if component in ("counts", "climate"):
            key = item["key"]
            require(isinstance(key, list) and len(key) == (2 if component == "counts" else 1), "Clave P6 inválida")
            source_week = _date(key[-1])
            require(through == source_week + timedelta(days=6), "P6 no acredita cierre semanal completo")
        attested.append({key: value for key, value in item.items() if key not in ("observed_through", "basis_ref")})
    require(sorted(canonical_bytes(item) for item in attested) == sorted(canonical_bytes(item) for item in inventory), "P6 no coincide con fechas/variables/claves declaradas")

    inputs = _DerivedInputs(tuple(radios), frames["counts"], frames["climate"], frames["territory"],
                            tuple(tuple(edge) for edge in graph["edges"]), graph_date, graph["source_ref"],
                            bundle["dataset_version"], kind, bundle["count_unit"])
    if provisional:
        inputs.experiment_mode = PROVISIONAL_EXPERIMENT
    inputs._source_refs = frozenset(value["provenance_ref"] for value in sources.values())
    inputs._window = (start, end, request.review_as_of)
    inputs.input_evidence = {"schema_version": bundle["schema_version"], "package_sha256": request.package_sha256,
                             "preparation_ref": request.preparation_ref, "decision_ref": request.decision_ref,
                             "evidence_refs": dict(refs), "review_as_of": request.review_as_of.isoformat(),
                             "document_sha256": {ref: documents[ref].sha256 for ref in reviewed_documents},
                             "training_authorized": provisional, "evaluation_authorized": provisional}
    if provisional:
        inputs.input_evidence.update(experiment_mode=PROVISIONAL_EXPERIMENT,
            historical_availability_accredited=False, production_inference_authorized=False,
            territory_version=bundle["territory_version"], target_definition=bundle["target_definition"],
            evaluation_mode=bundle["evaluation_mode"],
            authorization_basis=decision.get("authorization_basis", "external_provider_permission"),
            authorization_ref=decision.get("project_owner_declaration_ref") if owner_declaration else decision["provider_permission_ref"],
            local_experimental_only=True)
        if snapshot:
            inputs.input_evidence.update(snapshot_scenario=policy, conditional_on_observed_cells=False,
                                         local_retrospective_query_authorized=True)

    def recheck():
        _authorize(registry, request)
        if provisional:
            for item in upstream:
                for use in (AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING, AuthorizedUse.TRAINING, AuthorizedUse.EVALUATION):
                    permitted = registry.authorize(item["source_id"], sheet=item["sheet"], subset_ref=item["subset_ref"], use=use)
                    require(permitted.source_version == item["source_version"], "Versión aguas arriba fuera de permiso")
        # Releer sólo bytes en memoria detecta revocaciones/reemplazos del registro.
        for ref, (role, original) in reviewed_documents.items():
            require(_document(documents, ref, request, kind, role) == original, "Evidencia cambiada después de validar")

    inputs._recheck = recheck
    inputs._validated_sha256 = _fingerprint(inputs)
    inputs.validate()
    return inputs


def _check_episode_counts(evidence, counts):
    """Sólo conciliaciones agregadas P2; no identifica ni fusiona pacientes."""
    require(evidence.get("identity_policy_version") == PRINCIPAL_EPISODE_POLICY, "Falta política P2 de episodios revisada")
    items = evidence.get("identity_snapshots")
    require(isinstance(items, list) and len(items) == len(counts), "P2 no concilia todos los snapshots de conteos")
    inventory = {}
    for item in items:
        require(isinstance(item, dict) and set(item) == {"key", "available_on", "summary", "basis_ref"}
                and _text(item["basis_ref"]), "Conciliación P2 sin alcance o respaldo")
        key = item["key"]
        require(isinstance(key, list) and len(key) == 2 and _text(key[0]), "Clave de snapshot P2 inválida")
        snapshot_key = (key[0], _date(key[1]), _date(item["available_on"]))
        require(snapshot_key not in inventory, "Snapshot P2 repetido")
        summary = item["summary"]
        try:
            validate_episode_summary(summary)
        except ValueError as error:
            raise ForecastError("P2 no respalda la conciliación de registros/episodios") from error
        require(summary["review_available_on"] is None or _date(summary["review_available_on"]) <= snapshot_key[2],
                "Fuga temporal P2: revisión posterior al snapshot")
        inventory[snapshot_key] = summary
    for row in counts.itertuples():
        summary = inventory.pop((row.radio_id, row.week_start, row.available_on), None)
        require(summary is not None, "P2 fuera del alcance exacto del snapshot")
        if row.state == "complete":
            require(summary["exact_episode_count"] == row.count, "Conteo acreditado incompatible con episodios P2 o identidad pendiente")
        elif row.state == "provisional" and pd.notna(row.count):
            require(summary["eligible_records"] == row.count, "Conteo provisional incompatible con registros P2")
    require(not inventory, "P2 contiene snapshots ajenos")
