# API de SIGARD

FastAPI expone el alta anónima, seguimiento público y administración protegida
de reportes ciudadanos. Los reportes se almacenan en `citizen_reports`, sin
reutilizar tablas epidemiológicas.

## Puesta en marcha

La configuración Docker se está incorporando por etapas y se documenta en
[`docs/docker-development.md`](../docs/docker-development.md). Las variables
privadas se definen exclusivamente en el `.env` de la raíz, creado a partir de
`.env.example` y nunca versionado.

El orden previsto es iniciar PostgreSQL/PostGIS, ejecutar las migraciones con
Alembic y después iniciar Uvicorn sin registro de acceso. Las migraciones y la
retención se ejecutarán como trabajos independientes creados desde la misma
imagen del backend.

`AUTO_CREATE_SCHEMA=true` se reserva para desarrollo con una base vacía. En
producción se usan las migraciones. `CORS_ORIGINS` acepta orígenes separados por
coma y no debe usar comodines.

## Endpoints

```text
GET   /
GET   /health
GET   /health/ready
GET   /api/v1/public/weeks
GET   /api/v1/public/predictions/{cutoff_date}
GET   /api/v1/public/territorial-context
GET   /api/v1/public/experimental-spatial-history/{cutoff_date}
GET   /api/v1/public/metadata
GET   /api/v1/public/model-evaluation
POST  /api/v1/citizen-reports
GET   /api/v1/citizen-reports/status/{tracking_code}
POST  /api/v1/geocoding/address
POST  /api/v1/admin/session
GET   /api/v1/admin/citizen-reports
GET   /api/v1/admin/citizen-reports/export.csv
GET   /api/v1/admin/citizen-reports/{id}
PATCH /api/v1/admin/citizen-reports/{id}
```

Los endpoints epidemiológicos públicos leen exclusivamente el lote marcado
como `published`. Ese lote se carga fuera del proceso web mediante:

```powershell
docker compose -f compose.yaml run --rm publication-import
```

El importador valida alineación temporal, 263 radios, niveles relativos,
geometrías y ausencia de campos privados. La operación es transaccional e
idempotente; no entrena modelos ni modifica las fuentes.

La búsqueda de dirección requiere un consentimiento separado en el frontend y
se realiza desde la API: OpenStreetMap recibe el texto buscado y la IP del
servidor, nunca la IP del ciudadano. La consulta pública de estado nunca
devuelve texto, dirección ni coordenadas. Los
endpoints administrativos requieren JWT y rol `admin`, responden con
`Cache-Control: no-store` y registran cambios/exportaciones en auditoría.

## Pruebas y retención

```bash
pytest -q
python -m app.retention
```

La ejecución final de `pytest -q` completa **13 pruebas**. La migración también se
compiló en modo offline para PostgreSQL/PostGIS mediante Alembic.

La segunda orden debe programarse diariamente fuera del proceso web. El plazo
por defecto es 180 días. En Docker se ejecuta mediante el servicio temporal
`retention`; en producción debe configurarse un cron o tarea equivalente como
condición obligatoria de salida.

Los límites antiabuso en memoria sirven para una sola instancia del MVP. Antes
de escalar horizontalmente deben reemplazarse por un almacén efímero compartido
con HMAC rotativo y vencimiento corto, sin guardar la IP completa.
