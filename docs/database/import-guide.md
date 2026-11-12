# Instalación e importación privada

No usar la conexión de la API ni el PostgreSQL existente de 5432. Los comandos
se ejecutan desde la raíz de SIGARD, rama `entrenamiento-ML`, con Python ML.
Nunca copiar URLs con contraseña a la terminal, al informe público o a Git.

## Entorno

Se reutilizan las versiones SQLAlchemy, psycopg2 y Alembic del backend. El
extra `database` de `ml/pyproject.toml` las declara junto a openpyxl. En un
entorno ML congelado instalar sólo los paquetes faltantes, sin actualizar
scikit-learn, NumPy, pandas o las bibliotecas geográficas:

```powershell
.\ml\venv\Scripts\python.exe -m pip install SQLAlchemy==2.0.35 psycopg2-binary==2.9.12 alembic==1.14.0
```

## Clúster local aislado

En Ubuntu/WSL hacen falta PostgreSQL 16 y PostGIS 3. El script
`backend/database/epidemiology/install-wsl-packages.sh` es una instalación
explícita para una distribución sin clústeres: requiere root, no reemplaza
políticas de servicio existentes, impide el arranque y la creación del clúster
predeterminado. No ejecutarlo si ya existen esos paquetes o instalaciones.

```powershell
wsl.exe -d Ubuntu -u root -- bash /mnt/c/RUTA/AL/REPO/backend/database/epidemiology/install-wsl-packages.sh
.\ml\venv\Scripts\python.exe -B tools/epidemiology_local.py init
```

`init` genera credenciales ignoradas, rechaza datos existentes y crea
`sigard_epi_local_v1` y `sigard_epi_test_v1` en un clúster propio. Los datos se
guardan en `$HOME/.local/share/sigard-epi/cluster-v1` del usuario Linux, permisos
0700; no se registra un servicio. Las acciones posteriores son manuales:

```powershell
.\ml\venv\Scripts\python.exe -B tools/epidemiology_local.py start
.\ml\venv\Scripts\python.exe -B tools/epidemiology_local.py status
.\ml\venv\Scripts\python.exe -B tools/epidemiology_local.py stop
```

Si se utiliza otro archivo privado ya generado, añadir `--config RUTA_PRIVADA`.
`stop` conserva los datos. No usar `init` para reiniciar ni borrar el clúster.
No hay acceso a 5432 ni dependencia de Docker. No ejecutar estos comandos en
una base persistente ajena al clúster propio.

## Migrar

La variable se carga del archivo ignorado sin imprimir su contenido:

```powershell
$epiConfig = Get-Content -Raw -LiteralPath data/interim/official/database-local-v1/connection.private.json | ConvertFrom-Json
$env:SIGARD_EPI_DATABASE_URL = $epiConfig.url
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_import --migrate --report data/interim/official/NUEVA_ENTREGA/migration.private.json
```

Se usa `backend/alembic-epidemiology.ini` y el historial
`ingestion.schema_version`. Repetir upgrade es idempotente. Las migraciones
privadas no forman una segunda cabeza en el Alembic público; no crean ni
alteran las tablas de la API. Downgrade destructivo está deshabilitado.

## Fuentes y diccionario real

Origen predeterminado obligatorio: `<repo>/data/datos oficiales`. En este
proyecto corresponde al directorio original indicado por el responsable.
Puede declararse explícitamente con `--source-root` o
`SIGARD_SISA_SOURCE_ROOT`. Sólo se resuelven los cinco nombres SISA autorizados;
se admite la variante sin `(2)` en esa misma carpeta, sin buscar copias externas.
`--files NOMBRE.xlsx …` permite entregas posteriores dentro del mismo origen.

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_import --dry-run --report data/interim/official/NUEVA_ENTREGA/inventory.private.json
```

Dry-run no conecta ni escribe registros en la base. Produce un informe privado
con hojas, filas, tipos, nulos, fechas, identificadores repetidos y mapeo por
columna. Se conserva toda hoja no vacía; sin encabezado reconocible, todas sus
filas se preservan como pendientes de interpretación, incluida la primera.
Un nombre de archivo no se interpreta como período clínico ni cobertura.

## Autorizar y aplicar

El responsable prepara un JSON privado con `status="approved"`,
`purpose="private_normalized_ingestion"`, `authorization_ref`, `source_root`
y `files`, diccionario de nombre exacto a SHA-256 verificado. No publicar ese
manifiesto ni sus hashes. El importador comprueba hash y carpeta antes de leer.

El manifiesto puede añadir `source_metadata`, indexado por nombre de archivo,
con `procedencia` obligatoria y `fecha_extraccion` (fecha ISO),
`periodo_declarado` y `entrega_version` documentados. No se deducen del nombre.
Completar metadatos vacíos no altera bytes ni filas; un valor documentado en
conflicto requiere revisión y revierte la operación. La extracción nunca
rellena automáticamente `disponible_desde` de los registros.

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_import --apply --authorization data/interim/official/NUEVA_ENTREGA/authorization.private.json --report data/interim/official/NUEVA_ENTREGA/import.private.json
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_import --validate --report data/interim/official/NUEVA_ENTREGA/validation.private.json
```

Cada archivo se importa en una transacción: archivo completo, hojas/columnas,
staging, registro, fechas, clasificaciones, domicilio y geocodificación. Una
falla revierte ese archivo; los otros archivos posibles continúan. No se
descartan filas por faltantes: se preservan y se registran incidencias.
Reimportar bytes idénticos con el mismo importador no duplica registros y sólo
necesita comprobar su hash. Un archivo cambiado crea otra versión/lote.
Identificadores externos repetidos quedan relacionados, nunca como PK de caso.
Duplicados técnicos requieren igual payload tipado e igual disposición de
encabezados; no resuelven identidad epidemiológica de episodios.

## Contexto y clima

Las acciones explícitas `--load-territory --master ARCHIVO --master-sha256 HASH`
y `--assign-radios` del mismo CLI cargan el maestro y evalúan candidatos. La
selección V3 requiere además `--membership PARQUET --membership-sha256 HASH`;
se lee únicamente su columna `radio_id`, sin inferir miembros por códigos.
No se alteran las geometrías fuente. Un maestro cambiado requiere un universo
nuevo y revisión del contrato; no se mezcla en la versión existente.

`--load-climate --climate-package PAQUETE --climate-sha256 HASH
--climate-version VERSION` acepta agregados compatibles explícitamente
autorizados. Conserva llegadas desconocidas y rechaza cambiar la fuente dentro
de la misma versión. No incorpora fuentes meteorológicas nuevas por red.

## Ejecutar analítica desde la base

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_analytics --config data/interim/official/NUEVA_ENTREGA/analytics-config.private.json --report data/interim/official/NUEVA_ENTREGA/analytics.private.json
```

Contrato JSON: `status`, `authorization_ref`, `version`, `universe`, `start`,
`end`, `scenario` (`conservative` o `experimental_assumed`), `mode`
(`retrospective` o `as_of`), `cutoff` con zona horaria, `batch_ids`,
`accept_provisional_geography` y `climate_version` opcionales. Un escenario
asumido necesita `covered_weeks` explícitas y `coverage_ref`; no deriva su
alcance de semanas vacías o fechas extremas.

La cobertura respaldada se suministra mediante `coverage_claims`, con
`source_sha256`, `start`, `end`, `state`, `evidence` y `reviewer`, más
`population_definition` y `extraction_filters`. El estado es una revisión
declarada por el responsable, no una certificación automática del programa.
Se exige alcance completo para todas las fuentes seleccionadas bajo la misma
definición. No se debe marcar `verified` por conveniencia técnica.

Cada ejecución es inmutable y rechaza sobrescritura. Entregas nuevas necesitan
otra versión analítica y una selección de lotes. Si hay versiones del mismo
archivo, `batch_ids` es obligatorio; no se mezclan snapshots por orden de llegada.
La analítica no vuelve a leer Excel. API y modelos permanecen desconectados.

## Pruebas

La [revisión posterior a la importación](resolution-guide.md) usa
`sigard_ml.ingestion.db_resolution` y revisiones inmutables. No requiere repetir
la importación ni abrir los libros. Las configuraciones analíticas pueden fijar
`resolution_version`; los reportes y las declaraciones reales siguen excluidos
de Git. Las pruebas adicionales están en `ml/tests/test_epidemiology_resolution.py`
y utilizan la misma base ficticia PostGIS existente.

Configurar `SIGARD_EPI_DATABASE_URL` con `test_url`, nunca con `url` de datos
reales. Las pruebas rechazan nombres fuera de `sigard_epi_test_*` y clústeres
sin marcador propio. Sólo allí recrean los esquemas para fixtures ficticias:

```powershell
$env:SIGARD_EPI_DATABASE_URL = $epiConfig.test_url
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_epidemiology_database.py -p no:cacheprovider --basetemp=ml/.tmp/epi-db-tests
```

Sin PostgreSQL compatible las pruebas de integración se omiten explícitamente;
no se sustituyen por SQLite. El resultado real de una ejecución se registra
en el informe privado. Tras finalizar, limpiar la variable y detener el clúster
propio si no se lo seguirá usando. No borrar sus archivos ni las fuentes.
