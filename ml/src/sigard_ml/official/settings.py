"""Nombres y umbrales modificables del control preliminar; sin datos clínicos."""

import re
import unicodedata

REPORT_VERSION = "official-quality-0.2.0"
HEADER_SCAN_ROWS = 50
MIN_HEADER_MATCHES = 3
MIN_SAFE_COUNT = 5
DATE_MIN_YEAR = 1900
DATE_MAX_YEAR = 2100
LOW_PRECISION_DECIMALS = 3
CLASSIFICATION_LABELS = {
    "confirmado": "confirmed_label", "sospechoso": "suspected_label",
    "probable": "probable_label", "descartado": "discarded_label",
    "sin clasificar": "unclassified_label",
}
DATE_ABSENCE_MARKERS = {"0", "-", "s/d", "sd", "sin dato", "sin datos", "no informa", "no informado"}
DATE_FORMAT_PATTERNS = {
    "zero_date_placeholder_candidate": r"^0{4}-0{2}-0{2}",
    "iso_with_fractional_seconds": r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\.\d+",
    "iso_with_T_separator": r"^\d{4}-\d{2}-\d{2}T",
    "day_first_time_without_seconds": r"^\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}$",
}
PRECISION_LABEL_WORDS = {
    "address_word": {"address", "direccion", "domicilio", "rooftop", "house", "building"},
    "street_word": {"street", "calle"},
    "neighborhood_word": {"neighborhood", "suburb", "barrio"},
    "locality_word": {"locality", "localidad", "city", "ciudad"},
    "centroid_word": {"centroid", "centroide"},
    "interpolation_word": {"interpolation", "interpolada", "interpolado", "interpolacion"},
}
CLASSIFICATION_LABEL_WORDS = {
    "confirmed_word": {"confirmado", "confirmada"},
    "suspected_word": {"sospechoso", "sospechosa"},
    "probable_word": {"probable"},
    "discarded_word": {"descartado", "descartada"},
    "dengue_word": {"dengue"},
    "laboratory_word": {"laboratorio"},
}

# Aliases de encabezados, nunca de valores de pacientes. Cada entrega puede
# completar este catálogo o fijar columnas por índice en su configuración privada.
COLUMN_ALIASES = {
    "surname": ("apellido", "apellidos", "apellido y nombre", "apellidos y nombres"),
    "given_name": ("nombre", "nombres"),
    "document": ("dni", "documento", "nro documento", "numero documento", "nro de documento"),
    "event_id": ("id evento", "id de evento", "id_evento", "codigo evento", "id caso", "id notificacion"),
    "event": ("evento", "nombre evento", "grupo evento"),
    "classification": ("clasificacion", "clasificacion manual", "clasificacion final", "clasificacion del caso"),
    "algorithm_classification": ("clasificacion algoritmo", "clasificacion automatica"),
    "opened_on": ("fecha apertura", "fecha de apertura", "fecha notificacion", "fecha de notificacion"),
    "symptom_onset": ("fecha inicio sintomas", "fecha de inicio de sintomas", "fecha inicio de sintomas", "fis"),
    "sample_on": ("fecha toma muestra", "fecha de toma de muestra", "fecha muestra"),
    "updated_on": ("fecha ultima actualizacion", "fecha actualizacion", "fecha de actualizacion"),
    "birth_on": ("fecha nacimiento", "fecha de nacimiento"),
    "province": ("provincia residencia", "provincia de residencia", "provincia"),
    "department": ("departamento residencia", "departamento de residencia", "departamento"),
    "locality": ("localidad residencia", "localidad de residencia", "localidad"),
    "address": ("domicilio", "direccion", "calle", "calle residencia", "domicilio residencia", "domicilio corregido"),
    "phone": ("telefono", "celular", "tel"),
    "latitude": ("latitud", "latitude", "lat", "latitud aproximada"),
    "longitude": ("longitud", "longitude", "lon", "lng", "longitud aproximada"),
    "coordinate_pair": ("coordenadas", "coordenada", "coordenadas aproximadas"),
    "age": ("edad", "edad actual"),
    "sex": ("sexo", "sexo legal"),
    "coordinate_precision": ("precision geocodificacion",),
    "geocoding_status": ("estado geocodificacion",),
    "symptom_week": ("semana epidemiologica fis", "semana epi fis"),
    "sample_week": ("semana epidemiologica muestra", "semana epi muestra"),
}
SENSITIVE_FIELDS = {"surname", "given_name", "document", "address", "phone",
                    "birth_on", "latitude", "longitude", "coordinate_pair"}
DATE_FIELDS = ("opened_on", "symptom_onset", "sample_on", "updated_on")
HEADER_WORDS = set(" ".join(alias for aliases in COLUMN_ALIASES.values() for alias in aliases).split()) | set(
    "id idevento idcaso documento tipo numero nro n residencia notificacion carga apertura "
    "departamento provincia localidad pais establecimiento salud diagnostico automatico manual "
    "clasificacion resultado laboratorio muestra consulta internacion alta fallecimiento "
    "fecha inicio fin ultima actualizacion sintomas positivo negativo semana anio edad meses anos "
    "geocodificacion geocodificado geocodificada geocodificadas coordenada coordenadas "
    "coordenada latitude longitude lat lon lng x y gps wgs84 precision calidad metodo fuente "
    "estado status consulta query address confidence score corregida corregidas corregido "
    "calle calles altura barrio direccion normalizada normalizado original geocode geocoding "
    "observaciones completo completa decimal aproximada aproximado latitud longitud "
    "codigo codificacion epidemiologica epidemiologico confirmacion positivo caso evento "
    "snvs sisa salud nominal final paciente episodio notificado notificacion fechaabertura "
    "departamentoresidencia provinciaresidencia localidadresidencia fechaapertura tipoevento "
    "documento snvs nacionalidad ocupacion email mail telefono piso dpto cp postal cod "
    "nrodoc nrodocumento clasi clasif manual automatica lugar localidadnotificacion "
    "id_evento id_caso id_snvs toma diagnostico derivacion web coincidente encontrada "
    "nominatim lon_geo lat_geo utc agregado domicilio observacion referencia version "
    "establecimientonotificacion departamento departamental latitudaproximada longitudaproximada"
    .split()
)


def normalize_header(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def identify_column(value) -> str | None:
    label = normalize_header(value)
    for field, aliases in COLUMN_ALIASES.items():
        if label in {normalize_header(alias) for alias in aliases}:
            return field
    return None


def safe_header(value) -> str | None:
    """Sólo comunica términos de esquema de un vocabulario técnico cerrado."""
    label = normalize_header(value)
    words = label.split()
    if not words:
        return None
    visible = [word if word in HEADER_WORDS else "[masked]" for word in words]
    return " ".join(visible) if any(word in HEADER_WORDS for word in words) else None
