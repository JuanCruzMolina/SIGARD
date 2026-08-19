# API de SIGARD

FastAPI expone el alta anónima, seguimiento público y administración protegida
de reportes ciudadanos. Los reportes se almacenan en `citizen_reports`, sin
reutilizar tablas epidemiológicas.

## Puesta en marcha

1. Crear `.env` a partir de `.env.example` y reemplazar `SECRET_KEY` y las
   credenciales de bootstrap.
2. Iniciar PostgreSQL/PostGIS.
3. Ejecutar `alembic upgrade head` desde `backend/`.
4. Iniciar `uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`
   para que Uvicorn no persista direcciones IP en su registro de acceso.
5. Retirar `ADMIN_BOOTSTRAP_PASSWORD` después de crear el primer administrador.

`AUTO_CREATE_SCHEMA=true` se reserva para desarrollo con una base vacía. En
producción se usan las migraciones. `CORS_ORIGINS` acepta orígenes separados por
coma y no debe usar comodines.

## Endpoints

```text
GET   /
GET   /health
POST  /api/v1/citizen-reports
GET   /api/v1/citizen-reports/status/{tracking_code}
POST  /api/v1/geocoding/address
POST  /api/v1/admin/session
GET   /api/v1/admin/citizen-reports
GET   /api/v1/admin/citizen-reports/export.csv
GET   /api/v1/admin/citizen-reports/{id}
PATCH /api/v1/admin/citizen-reports/{id}
```

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

La ejecución final de `pytest -q` completa **9 pruebas**. La migración también se
compiló en modo offline para PostgreSQL/PostGIS mediante Alembic.

La segunda orden debe programarse diariamente fuera del proceso web. El plazo
por defecto es 180 días. En el despliegue incluido, `docker compose up --build`
espera a que PostgreSQL esté disponible, ejecuta las migraciones y levanta el
servicio `retention`, que realiza la purga al iniciar y luego cada 24 horas. En
otra plataforma debe configurarse un cron o tarea equivalente como condición
obligatoria de salida a producción.

Los límites antiabuso en memoria sirven para una sola instancia del MVP. Antes
de escalar horizontalmente deben reemplazarse por un almacén efímero compartido
con HMAC rotativo y vencimiento corto, sin guardar la IP completa.
