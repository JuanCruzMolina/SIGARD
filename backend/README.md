# API de SIGARD

FastAPI expone el alta anónima, seguimiento público y administración protegida
de reportes ciudadanos. Los reportes se almacenan en `citizen_reports`, sin
reutilizar tablas epidemiológicas.

La consulta retrospectiva A/B tiene un [launcher de investigación exclusivamente
local](../docs/experimental-spatial-local.md). El arranque habitual no registra
sus rutas; no habilitarla en Docker ni en despliegues públicos.
El mapa local A/B consulta agregados sin autenticación, cookies ni diálogos de
Windows. Su instancia FastAPI fija `127.0.0.1:8765`, sin base de datos ni claves,
y sólo permite lectura desde Vite en `127.0.0.1:5173`. La administración habitual
de reportes conserva su autenticación; ver la guía anterior.

El panel local de análisis reutiliza esa instancia con dos consultas GET de
sólo lectura: `/api/v1/research/spatial/evaluation` proyecta las seis métricas
comparativas A/B ya guardadas por partición, y
`/api/v1/research/spatial/history/{radio_censal}` devuelve los scores congelados
de un radio en las semanas disponibles. Conservan las mismas comprobaciones
de integridad, acceso loopback, Origin, marcador local y `no-store`. No cargan
modelos ni recalculan métricas. La ausencia de métricas autorizadas produce 404;
un artefacto incompatible produce 503. El contrato público no cambia. Ver el
[contrato experimental](../docs/experimental-spatial-results-contract.md).

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
GET   /api/v1/admin/users
POST  /api/v1/admin/users
POST  /api/v1/admin/users/{id}/deactivate
POST  /api/v1/admin/users/{id}/password
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

## Cuentas administrativas y autenticación — etapa 14

Se reutilizan `usuarios`, PBKDF2-SHA256 de Passlib, JWT firmado con vencimiento
y rol `admin`. `get_current_user` autentica firma, vencimiento, cuenta activa y
versión de sesión; `get_current_admin` autoriza según el rol vigente en la base.
Todos los administradores activos tienen los mismos permisos de gestión: no
se incorpora un rol superior ni registro público. La interfaz está en
`/admin/reportes` → **Gestionar cuentas**, con la misma sesión existente.

- `GET /users`: listado paginado de administradores, estado y cuenta actual;
  nunca devuelve hashes, versiones de sesión o tokens.
- `POST /users`: `email`, `password`, `current_password` del administrador que
  actúa. Normaliza el correo y rechaza duplicados, incluso de cuentas inactivas
  o de otros roles. No permite asignar rol, estado ni versión desde el payload.
- `POST /users/{id}/deactivate`: `current_password`. Bloquea el login y todos
  los tokens de la cuenta; nunca desactiva el último administrador activo.
  Puede desactivarse la cuenta propia si queda otra activa; la interfaz cierra
  su sesión. Repetir la desactivación no duplica la auditoría.
- `POST /users/{id}/password`: `current_password` de quien autoriza y
  `new_password` para la cuenta indicada. Permite cambio propio o restablecimiento
  por otro administrador activo; no requiere conocer la contraseña anterior del
  destinatario. La nueva debe ser diferente. Invalida todos sus tokens previos;
  si es la cuenta propia exige volver a ingresar. No reactiva cuentas inactivas.

Las rutas anteriores tienen prefijo `/api/v1/admin`. Se conserva el límite de
contraseñas de 8–200 caracteres. La confirmación visual se acompaña de
reautorización en el servidor; los campos se limpian tras la solicitud. Se
reutiliza el limitador existente para las operaciones de cuentas, con alcance
separado y `ADMIN_LOGIN_RATE_LIMIT` por 15 minutos. Los errores de validación
administrativos no reflejan el payload. No hay recuperación por correo, envío
de credenciales, contraseñas visibles ni servicios externos. El uso operativo
continúa requiriendo HTTPS y resguardo de secretos del entorno; no se cambió
su configuración en esta etapa.

Cada cambio registra actor, destinatario, acción y fecha en `admin_account_audit`,
dentro de la misma transacción. La auditoría no almacena contraseñas, hashes ni
tokens. Desactivación y rotación incrementan `usuarios.token_version`; en cada
solicitud se compara el claim JWT `ver` con la base. Los tokens anteriores a esta
migración, sin ese claim, requieren nuevo login.

Los cambios de cuentas se serializan mediante un bloqueo transaccional advisory
de PostgreSQL compartido por los workers; las pruebas SQLite usan `BEGIN IMMEDIATE`.
Después de adquirir el bloqueo se vuelve a comprobar el actor, evitando que una
solicitud que esperó detrás de una revocación siga autorizada. El conteo de
administradores se realiza dentro de esa transacción.

### Migración y bootstrap

`migrations/versions/20261020_04_admin_accounts.py` añade la versión de sesión,
el índice único `lower(trim(email))` y la auditoría, con downgrade inverso. Está
**preparada y no aplicada a ninguna base persistente**. Antes de aplicarla, un
operador autorizado debe resolver posibles duplicados históricos de correo;
la migración no fusiona ni corrige cuentas automáticamente. Desplegar el código
junto con el esquema correspondiente: `/health/ready` devuelve 503 si falta.
El downgrade elimina la auditoría y las versiones; sólo se probó en bases
ficticias, no se ejecutó contra una instalación.

El bootstrap ahora crea únicamente la primera cuenta cuando `usuarios` está
vacía, bajo el mismo bloqueo. No restablece contraseñas ni recrea privilegios
si ya existen usuarios. Tras ese alta inicial, retirar `ADMIN_BOOTSTRAP_PASSWORD`
del entorno por el procedimiento operativo autorizado. No se editó `.env`.
Si se pierde acceso a todos los administradores, no hay recuperación anónima:
se requiere intervención del operador autorizado fuera de este flujo.

Para ensayar la reversión administrativa, detener la API y usar exclusivamente
una base de pruebas autorizada indicada por `DATABASE_URL`. Desde `backend/`,
`python -m alembic downgrade 20260924_03` retira sólo la migración de cuentas;
`python -m alembic upgrade head` la reaplica. Verificar que usuarios y hashes se
conserven y que reaparezcan columna, índice y tabla de auditoría. El código actual
necesita el esquema actualizado para iniciar sesión. El downgrade elimina auditoría
y versiones de revocación: para restaurar el servicio después de revertir/reaplicar,
un operador autorizado debe invalidar los JWT anteriores mediante rotación de la
clave de firma. No se realizó esa operación ni se modificó `.env` en esta revisión.

En etapa 15 se probó aplicar→revertir→reaplicar la última migración en SQLite
ficticio con usuarios preexistentes y duplicados normalizados; la cadena Alembic
completa generó SQL PostgreSQL de subida/reversión sin conexión. La prueba real
opcional `test_postgresql_isolated_migration_integrity_revocation_and_concurrency`
se omite sin `SIGARD_TEST_POSTGRES_URL`. Exige base vacía y rol
`sigard_stage15_test`, host `127.0.0.1` y puerto distinto de 5432/5433. No crea ni
inicia un servidor: requiere autorización previa para un clúster descartable.
No se ejecutó en PostgreSQL en esta etapa; el servicio nativo existente no se
utilizó. Ver el bloqueo y el alcance pendiente de PostGIS en la matriz del MVP.

### Ensayo PostgreSQL/PostGIS descartable — preparación de etapa 16

**Procedimiento preparado, no ejecutado. Requiere autorización explícita antes
de iniciar un clúster, contenedor o servicio.** Queda prohibido conectar a bases
de `127.0.0.1:5432`; tampoco reutilizar 5433 ni el volumen `database_data` de
Compose. No se inspeccionó el contenido de esas bases. Los puertos siguientes
son propuestas: comprobar que estén libres y detener el procedimiento si no lo
están, sin cerrar procesos ajenos ni sustituir destinos automáticamente.

**Opción nativa administrativa:** están disponibles `initdb`, `pg_ctl`, `createdb`
y `psql` de PostgreSQL 18 bajo `C:/Program Files/PostgreSQL/18/bin`. Reservar
`127.0.0.1:5434` y un directorio nuevo `backend/.tmp/pg-stage16-disposable`;
no registrar un servicio Windows. Después de autorizar, el operador puede usar
`initdb -D <ruta-absoluta-nueva> -U sigard_stage15_test --auth=scram-sha-256 --pwprompt`
con contraseña efímera ficticia y `pg_ctl -D <misma-ruta> -l <log-temporal>
-o "-h 127.0.0.1 -p 5434" -w start`. Verificar el listener y limitar `pg_hba.conf`
a loopback. Crear con `createdb -h 127.0.0.1 -p 5434 -U sigard_stage15_test`
la base vacía `sigard_stage15_test`. La contraseña se proporciona por prompt o
`PGPASSWORD` efímero, nunca en la URL, documentación, logs o archivos del producto.
El nombre conserva el contrato estricto de la prueba existente, no identifica
una base operativa. Esta opción no comprueba geometrías: no se encontraron
archivos de extensión PostGIS en esa instalación.

**Opción geoespacial:** reutilizar la imagen declarada por el proyecto
`postgis/postgis:17-3.5`, con autorización adicional para Docker/descarga si
corresponde. Crear un contenedor independiente llamado `sigard-stage16-postgis`,
etiqueta `sigard.stage16=disposable`, publicación **127.0.0.1:5435:5432**, y
`--tmpfs /var/lib/postgresql/data:rw`. No montar rutas del host, fuentes médicas,
modelos ni volúmenes nombrados. Usar `--rm`, rol `sigard_stage15_test`, base
inicial `sigard_stage16_schema` y contraseña efímera vía variable
`POSTGRES_PASSWORD` heredada por el contenedor; no pasar su valor en el comando.
La disponibilidad/descarga de la imagen y este arranque no están verificados.
Confirmar listener loopback, identidad de rol/base y `SELECT postgis_version()`;
crear la extensión en la base de esquema si aún no existe. Un fallo detiene el
ensayo; nunca se recurre al servicio de 5432.

**Dos bases separadas dentro del entorno autorizado:**

1. `sigard_stage16_schema`: ensayo de las cuatro migraciones con PostGIS. Con
   API detenida, `AUTO_CREATE_SCHEMA=false`, configuración efímera de prueba y
   `DATABASE_URL` explícito al puerto 5435, ejecutar desde `backend/`
   `python -m alembic upgrade head`, `python -m alembic current`,
   `python -m alembic downgrade base` y nuevamente `python -m alembic upgrade head`.
   No usar secretos/bootstrap de la instalación ni cargar `.env` operativo;
   el operador debe suministrar una configuración de pruebas aislada.
   Confirmar revisión `20261020_04`, índices/FK/defaults, `POINT`/SRID 4326
   calculado de un reporte ficticio y geometrías territoriales. Importar sólo
   `frontend/public/data/` ya aprobado si se ensaya la publicación, nunca A/B
   privados. Falta ejecutar esa integración: SQL offline no la acredita.
2. `sigard_stage15_test`: base **vacía**, creada aparte, sin aplicar Alembic antes
   de la prueba siguiente. Ésta construye usuarios heredados ficticios y aplica,
   revierte y reaplica sólo la migración administrativa. El esquema completo
   anterior la haría fallar deliberadamente. Ejemplo desde la raíz, únicamente
   después de autorizar y verificar el destino:

   ```powershell
   $env:SIGARD_TEST_POSTGRES_URL = 'postgresql+psycopg2://sigard_stage15_test@127.0.0.1:5435/sigard_stage15_test'
   .\backend\.venv\Scripts\python.exe -B -m pytest backend/tests/test_admin_accounts.py -k postgresql_isolated -q -p no:cacheprovider --basetemp backend/.tmp/stage16-pg-test
   Remove-Item Env:SIGARD_TEST_POSTGRES_URL
   ```

   Para la opción nativa usar explícitamente 5434. `PGPASSWORD` sólo vive durante
   el ensayo. La prueba exige identidad/base vacía antes de mutar y fija timeouts;
   verifica unicidad normalizada, NOT NULL, FK, login, rotación y revocación de JWT.
   Dos solicitudes ya autenticadas se sincronizan con barrera y compiten por
   `pg_advisory_xact_lock(1397311297)` en conexiones distintas. En desactivación
   propia se esperan 200/409; cruzada 200/401 por revalidación del actor tras
   esperar. Siempre debe quedar exactamente un administrador activo. Guardar
   recibo del motor/resultado antes de afirmar concurrencia PostgreSQL comprobada.

La reversión sólo de cuentas y sus consecuencias para auditoría/tokens están
descritas arriba; no debe ejecutarse con la API recibiendo peticiones. Para
repetir el ensayo administrativo se necesita otra base vacía del mismo contrato
en un clúster nuevamente descartable, no reutilizar residuos de una ejecución.

**Limpieza:** cerrar API/pytest y sus conexiones. Para el nativo, usar `pg_ctl -D
<ruta-absoluta-verificada> -m fast -w stop`; confirmar cierre de 5434 y borrar sólo
el directorio nuevo cuya ruta resuelta esté dentro de `backend/.tmp/`. Para el
contenedor, verificar nombre/etiqueta/montajes antes de `docker stop
sigard-stage16-postgis`: `--rm` y tmpfs eliminan contenedor/datos. Confirmar que no
quedaron contenedor, listener 5435 ni volumen creado. Retirar las variables
efímeras de contraseña/URL/clave y conservar sólo resultados sin secretos. No
usar comandos globales de limpieza, detener el servicio existente ni borrar
volúmenes del proyecto. Ninguna acción de este procedimiento se ejecutó en etapa 16.

### Evidencia de etapa 14

`tests/test_admin_accounts.py` verifica altas/permisos, duplicados, validación
segura, reautorización y límites, revocación de tokens/contraseñas, última cuenta,
desactivaciones simultáneas y revocación durante espera, bootstrap, readiness y
migración reversible. Se usan bases SQLite ficticias y SQL PostgreSQL offline.
Las comprobaciones HTTP con navegador se ejecutan mediante
`npm.cmd --prefix frontend run test:accounts:browser`, con Vite ya activo y
`SIGARD_BROWSER_MODULE` apuntando a una instalación local existente de Puppeteer
si no está disponible por resolución normal de Node. No se añadió esa dependencia
al producto. El script inicia `tests/browser_admin_fixture.py` en un puerto
loopback libre, redirige sólo las solicitudes de prueba a esa API y elimina la
base temporal al cerrar. No lee `.env` ni utiliza la base de la instalación.

El ciclo interfaz→HTTP→persistencia se verificó completo con esa base descartable.
Docker/PostGIS no se iniciaron: migración, integración y bloqueo entre workers en
PostgreSQL operativo quedan pendientes. Ver resultados en la
[matriz funcional](../docs/mvp-functional-status.md).

## Pruebas y retención

Desde la raíz, para comprobar la proyección y las restricciones del análisis
experimental con fixtures ficticias:

```powershell
.\backend\.venv\Scripts\python.exe -B -m pytest backend/tests/test_experimental_results.py -q -p no:cacheprovider --basetemp backend/.tmp/analysis-pytest
```

```bash
pytest -q
python -m app.retention
```

En una validación anterior del backend se aprobaron **13 pruebas**,
correspondientes al alcance implementado en ese momento. Durante la etapa 11
se verificó una selección de **49 pruebas de backend**, con bases y artefactos
ficticios. Estas cifras describen el alcance de cada revisión y no acreditan
la totalidad de las pruebas existentes del proyecto. La migración también se
compiló en modo offline para PostgreSQL/PostGIS mediante Alembic.

La segunda orden debe programarse diariamente fuera del proceso web. El plazo
por defecto es 180 días. En Docker se ejecuta mediante el servicio temporal
`retention`; en producción debe configurarse un cron o tarea equivalente como
condición obligatoria de salida.

Los límites antiabuso en memoria sirven para una sola instancia del MVP. Antes
de escalar horizontalmente deben reemplazarse por un almacén efímero compartido
con HMAC rotativo y vencimiento corto, sin guardar la IP completa.
