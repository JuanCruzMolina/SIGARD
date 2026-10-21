# API de SIGARD

FastAPI expone el alta anónima, seguimiento público y administración protegida
de reportes ciudadanos. Los reportes se almacenan en `citizen_reports`, sin
reutilizar tablas epidemiológicas.

La consulta retrospectiva A/B tiene un [launcher de investigación exclusivamente
local](../docs/experimental-spatial-local.md). El arranque habitual no registra
sus rutas; no habilitarla en Docker ni en despliegues públicos.

**Integración descartable verificada (etapa 17):** PostgreSQL 17.5/PostGIS 3.5.2,
cadena Alembic completa reversible, cuentas/concurrencia, reportes y geometrías
ficticias. Ver [procedimiento y límites](#ensayo-postgresqlpostgis-descartable--etapa-17).
Esto no despliega la API persistente ni modifica `npm.cmd --prefix frontend run dev`.

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

La bandeja y `GET /api/v1/admin/citizen-reports/export.csv` admiten los mismos
filtros opcionales `category`, `status`, `neighborhood`, `date_from` y `date_to`.
Las fechas mantienen días UTC inclusivos; un rango invertido devuelve 422.
CSV exporta todos los resultados filtrados, sin paginación, y audita su cantidad;
sin filtros conserva la exportación completa. Requiere JWT/rol administrador.
El alta y la búsqueda de dirección validan longitud después de normalizar espacios;
un texto vacío normalizado no se persiste ni se consulta al geocodificador.

## Verificación ficticia del importador territorial — sin Docker

El importador vigente es `app/publication_import.py`, independiente de la
ingestión epidemiológica oficial de `sigard_ml.official`. El recorrido productivo
es: exportación offline (`sigard_ml.export.frontend_mvp`) → seis contratos →
`load_and_validate` → `import_publication` → tablas de publicación → consultas
de `app/public.py`. En este ensayo se genera la entrada desde constantes; no se
ejecuta la exportación ni se leen sus fuentes, cartografía o productos A/B.

Admite `available_weeks.json`, `temporal_predictions.json`,
`territorial_context.geojson`, `experimental_spatial_history.geojson`,
`model_evaluation.json` y `mvp_metadata.json`. Conserva el contrato de **263
radios**, una predicción departamental por semana y simulaciones espaciales
referenciadas al mismo radio/geometría y semana. No es un importador genérico
de polígonos, no carga modelos A/B ni aplica elegibilidad epidemiológica oficial.

Antes de abrir la base valida archivos, JSON legible sin claves duplicadas ni
números no finitos, objetos/Features, campos obligatorios, identificadores
textuales de hasta 32 caracteres, claves únicas, cobertura radio-semana y fechas
alineadas. Valida conteos enteros sin truncamiento, población/hogares/viviendas
no negativos, superficie positiva, percentiles entre 0 y 100, niveles admitidos
y scores experimentales/predicciones no negativos. Los otros componentes deben
ser finitos; no se agregan umbrales epidemiológicos ni rangos de score inexistentes.

Admite Polygon/MultiPolygon no vacíos con anillos cerrados de al menos cuatro
posiciones y coordenadas finitas dentro del rango WGS84. Sin `crs` rige el orden
longitud/latitud de GeoJSON. Para el miembro legado `crs` acepta `EPSG:4326`,
`urn:ogc:def:crs:EPSG::4326` y `urn:ogc:def:crs:OGC:1.3:CRS84`; rechaza otros
CRS en colección, Feature o geometría. **No reproyecta.** En producción almacena
con `ST_GeomFromGeoJSON`/`ST_SetSRID(...,4326)` y comprueba topología mediante
`ST_IsValid` antes de publicar. La validación estructural Python no certifica
autointersecciones, huecos o solapamientos internos.

Conserva SHA-256 de nombres y bytes de los seis archivos, versión explícita o
`mvp-<12 caracteres del hash>`, metadatos MVP/modelo y evaluación. Cambiar formato
o metadatos cambia el hash. Metadatos y evaluación deben ser objetos JSON; el
contrato no exige un esquema completo de procedencia ni una versión interna.
Se preservan las propiedades territoriales admitidas; atributos adicionales de
Features no se incorporan automáticamente a tablas o respuestas. La lista
recursiva de campos privados prohibidos no certifica autorización epidemiológica.

Una transacción retira el lote publicado anterior, crea el nuevo como `staged`,
inserta semanas, predicciones, radios y simulaciones, verifica geometrías y lo
marca `published`. Un error revierte esas operaciones. Repetir un hash publicado
devuelve el mismo ID sin insertar; un hash existente `staged`/`retired` se rechaza
y no se republica. Una versión usada con otro hash viola la unicidad y revierte.
El importador no tiene una aprobación separada: **publica en su base de destino
si termina correctamente**. Aquí el destino es exclusivamente SQLite descartable.

Desde la raíz, con las dependencias ya instaladas:

```powershell
# Pruebas focalizadas del importador
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py
# Regresión backend con el mismo aislamiento
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py --backend-regression
```

El ejecutor deshabilita `.env`, elimina destinos PostgreSQL heredados y bloquea
conexiones SQLAlchemy distintas de SQLite y llamadas directas al ejecutable
Docker. No usa el CLI del importador con configuración del entorno ni inicia
servidores. `publication_fixture.py` genera 263 cuadrados ficticios (uno como
MultiPolygon), IDs `TEST-0000` a `TEST-0262` y una semana de enero de 2030. Es la
cantidad mínima compatible; no usa aleatoriedad ni cambia el universo productivo.
Declara condición sintética, procedencia, período, unidad, CRS y versión de
transformación. Los archivos se escriben sólo bajo el temporal de pytest; la
base SQLite se elimina al finalizar cada prueba. No se escribe en `frontend/public`.

El adaptador contiene cuatro funciones espaciales SQLite limitadas a transportar
GeoJSON de las geometrías conocidas de la fixture e inyectar un veredicto de
validez. Ejecuta **el importador real y transacciones/constraints/FK de SQLite**;
no implementa PostGIS, ni acredita topología/SRID reales. Las consultas usan las
funciones y el router público existentes con TestClient en memoria, sin publicar
en la aplicación principal. Se comprueban lote válido e inválidos, idempotencia,
retiro del anterior, rollback después de insertar radios y ante rechazo geométrico
inyectado, ausencia de filas parciales, GeoJSON/atributos/versiones, errores
404/422/503 y exclusión de lotes `staged`/`retired`.

**Defectos corregidos:** CRS incompatibles ignorados, JSON ambiguo/no finito y
validación incompleta de estructura geométrica, campos, tipos/rangos y objetos
de metadatos. Ahora se rechazan con `ValueError` y contexto del campo antes de
abrir la base. Se mantienen esquema, migraciones, SQL, API y arquitectura.

**Pendiente:** ejecutar este mismo lote mediante `import_publication` en un
PostGIS descartable autorizado: conversión/SRID, rechazo topológico real,
rollback y lectura GeoJSON. La etapa 17 comprobó migraciones, GiST, SRID,
geometrías y rutas cargadas directamente; no ejecutó este importador. Shapely
instalado comprobó por separado 263 geometrías ficticias válidas y un control de
autointersección inválido; no equivale a ejecutar PostGIS. Resultados y estado
Docker en la [consolidación técnica](../docs/technical-consolidation.md).

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
No se ejecutó en PostgreSQL en etapa 15; el servicio nativo existente no se
utilizó. En etapa 17 se ejecutó mediante el entorno descartable de abajo.
La prueba ahora exige exactamente 5435 y la identidad efímera del clúster;
no ejecutarla configurando una URL manual de una instalación existente.

<a id="ensayo-postgresqlpostgis-descartable--preparación-de-etapa-16"></a>

### Ensayo PostgreSQL/PostGIS descartable — etapa 17

Ejecutado con autorización específica, sólo con datos y geometrías ficticios.
Se reutilizó la imagen local `postgis/postgis:17-3.5`: **PostgreSQL 17.5 y
PostGIS 3.5.2**. Contenedor independiente `sigard-stage17-postgis`, sin Compose,
publicación exclusiva `127.0.0.1:5435:5432`, `--rm`, reinicio `no` y `tmpfs` en
`/var/lib/postgresql/data`, sin binds ni volúmenes compartidos.
No se consultó ni utilizó el servidor existente de 5432.

Referencia del procedimiento ejecutado en etapa 17, no una autorización vigente:
Docker debe permanecer apagado. Una repetición futura requiere autorización
específica; estos comandos no se ejecutaron durante la consolidación actual.
El ensayo requiere Docker ya disponible y los puertos 5435/5174 libres:

```powershell
.\backend\.venv\Scripts\python.exe -B backend/tests/postgis_disposable.py
# Opcional: mismo ensayo más navegador, Vite temporal y API propia.
.\backend\.venv\Scripts\python.exe -B backend/tests/postgis_disposable.py --browser
```

El navegador reutiliza Puppeteer instalado mediante `SIGARD_BROWSER_MODULE`
si no está resoluble normalmente; no instala dependencias. El ejecutor no inicia
Docker Desktop ni servicios existentes. Durante aquella revisión, iniciar Docker
reactivó automáticamente dos contenedores preexistentes de SIGARD. La revisión
posterior encontró el motor apagado y no pudo comprobar su estado individual;
el usuario decidió conservar Docker apagado. No se consultaron sus bases ni se
eliminaron recursos ajenos. Esta incidencia es distinta del aislamiento comprobado
del contenedor de pruebas; no queda autorización pendiente para iniciar Docker.

**Barreras antes de migrar:** rama exacta, puerto libre, nombre inexistente,
imagen local, identidad/etiqueta del contenedor, bind loopback y tmpfs exclusivo.
Sólo admite `postgresql+psycopg2`, host literal `127.0.0.1`, puerto **5435**,
rol ficticio `sigard_stage15_test` y las dos bases permitidas. Rechaza URL con
contraseña/query y cualquier otro destino, incluido 5432/5433. Limpia variables
libpq heredadas; contraseña y clave JWT se generan sólo en memoria/entorno de
procesos propios. `Settings` no carga `.env`. Un guard intercepta conexiones
PostgreSQL antes de abrir la red; después se comprueban usuario, base y
`cluster_name` único. No usa auto-creación de esquema en PostgreSQL.

Dos bases dentro de la misma instancia descartable:

- `sigard_stage16_schema`: cuatro revisiones en orden `20260819_01` →
  `20260923_02` → `20260924_03` → `20261020_04`; downgrade hasta base y
  reaplicación. Nueve tablas de aplicación, índices, relaciones, defaults,
  `token_version`, unicidad normalizada y auditoría. Las tablas auxiliares de
  extensiones no se confunden con tablas de SIGARD.
- `sigard_stage15_test`: vacía desde `template0`, sólo para la prueba existente
  de cuentas heredadas ficticias, migración 04/reversión/reaplicación, NOT NULL,
  unicidad y FK. No reutilizar bases con residuos.

**Resultado final: 56 pruebas aprobadas, cero fallidas/omitidas.** Incluye siete
destinos rechazados sin conexión, JWT vencido/firma inválida, roles, revocación,
desactivación, rotación/restablecimiento y persistencia tras otra instancia de API.
Desactivaciones concurrentes propias/cruzadas usan dos `pg_backend_pid()`
diferentes y conservan un administrador activo: 200/409 en propias y 200/401
en cruzadas. Otra prueba observa espera real mediante `pg_blocking_pids`, revoca
al actor durante ella y obtiene 401 tras liberar el advisory lock.

PostGIS: punto generado de reporte con SRID 4326, orden longitud/latitud;
polígono ficticio mediante SQLAlchemy, interior/borde, `ST_Contains`/`ST_Covers`,
rechazo de SRID incorrecto, restricción de población, índice GiST utilizado con
exploración secuencial deshabilitada para ese ensayo y proyección GeoJSON en
rutas públicas. No acredita rendimiento ni importación/integración completa
de la cartografía oficial de 263 radios.

**Nueve grupos de navegador aprobados**, sin excepciones JS/advertencias React,
a 1440/390 px: formulario → HTTP/FastAPI → PostgreSQL → seguimiento, revisión/
exportación y ciclo de cuentas. El harness redirige sus solicitudes a su API
loopback propia y usa Vite temporal en 5174. Las respuestas de negocio provienen
del backend real; sólo se conserva la inyección explícita de un error 503 para
probar reintento. No comprueba A/B ni carga sus artefactos en este modo, y bloquea
solicitudes externas. El frontend de producto y el comando habitual no cambian.

Defecto real corregido: el formulario completo enviaba `possible_duplicate_of`
vacío y PostgreSQL lo rechazaba por FK. `admin.update_report` normaliza únicamente
ese vacío a NULL; una prueba elimina una referencia previa y comprueba persistencia.
Sin cambios de contratos, dependencias o historial de migraciones.

Regresión: 87 backend aprobadas y seis omitidas por no disponer del clúster en esa
ejecución (cinco PostGIS y la prueba PostgreSQL existente, ejecutadas arriba);
una prueba focalizada posterior de errores/permisos también aprobada en SQLite.
Seguridad: 135 controles del repositorio y 15 de recursos frontend; 18 pruebas del
coordinador. Lint y recursos aprobados. No sumar selecciones solapadas como casos
únicos. El caso del árbol de procesos falló dentro del sandbox y pasó fuera sin
cambiar código. Se conservan advertencias de deprecación; no se entrenó ML.

Los intentos iniciales corrigieron el harness: representación tmpfs, sintaxis,
alcance de introspección y conversión de resultados SQLAlchemy. El primer navegador
expuso el defecto FK y falló antes de corregirlo. No se presentan esos intentos
como aprobados. Recibos/JUnit sin secretos: `backend/.tmp/postgis-integration/`;
navegador: `frontend/.tmp/stage17-browser-result.json`, excluidos de Git/Docker.

**Limpieza propia comprobada:** Vite/API/navegador propios cerrados; contenedor
identificado por ID/etiqueta eliminado junto a ambas bases en tmpfs. Puertos
5435/5174 libres, sin volúmenes de datos creados. Credenciales retiradas del entorno
propio, sin persistirlas. Sólo quedan pruebas, recibos y documentación; no se usan
`prune`, limpiezas generales ni `.env` de la instalación. La restitución de los dos
contenedores reactivados por Docker no pudo comprobarse individualmente con el
motor apagado. La verificación anterior se dio por terminada conservando ese
estado; no se afirma restauración global.


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
