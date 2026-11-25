# Manual de instalación y operación técnica

SIGARD · Prototipo académico · `v1.0.0` (noviembre de 2026)
Sistema operativo de referencia: **Windows 11** con PowerShell. Todos los comandos se ejecutan
**desde la raíz del repositorio**, salvo que se indique otra carpeta.

> **Reglas que no se negocian**
> - Docker Desktop permanece **apagado**: no se usa para instalar, probar ni inspeccionar.
> - No se usa el PostgreSQL que pueda existir en `127.0.0.1:5432`. La base de investigación
>   corre en un clúster propio en `127.0.0.1:55439`.
> - Ningún secreto, contraseña, `.env`, dato, modelo ni archivo `*.private.*` se versiona ni se
>   escribe en documentación.
> - `dev` y `dev:demo` comparten el puerto 5173: **nunca se ejecutan en paralelo**. `dev:alerts` es un
>   alias obsoleto de `dev`.

## 1. Requisitos

| Componente | Versión usada | Para qué |
|---|---|---|
| Git | cualquiera reciente | Clonar el repositorio |
| Node.js y npm | Node 24 (probado con 24.15.0) | Frontend React/Vite y pruebas de navegador |
| Python | 3.12 (el paquete ML exige ≥ 3.11) | Backend FastAPI y paquete ML |
| WSL con Ubuntu | WSL 2 | Sólo para la base de investigación PostgreSQL 16 / PostGIS 3 |
| Puppeteer 25.9.0 y su Chrome | se instalan con el frontend (§2.1) | Sólo para las pruebas de navegador |

Para la demostración ficticia (`dev:demo`) alcanza con Node y Python: no hace falta PostgreSQL.

## 2. Clonar y preparar los entornos

```powershell
git clone <url-del-repositorio> SIGARD
cd SIGARD
git switch entrenamiento-ML
```

### 2.1 Frontend

```powershell
npm.cmd --prefix frontend ci
```

`npm ci` instala también Puppeteer **25.9.0** (dependencia de desarrollo con versión exacta; no
llega al bundle publicado). Su paso de instalación descarga el navegador de las pruebas en la caché
del usuario, fuera del repositorio: Chrome for Testing y Chrome Headless Shell 152.0.7977.54 en
`%USERPROFILE%\.cache\puppeteer\` (unos 700 MB en total); si ya están, los reutiliza. Sin conexión o
detrás de un proxy, se puede instalar sin la descarga (`$env:PUPPETEER_SKIP_DOWNLOAD='true'`) y
bajar el navegador después con
`node frontend/node_modules/puppeteer/lib/puppeteer/node/cli.js browsers install chrome`.
Sólo lo usan las pruebas de navegador (§9).

### 2.2 Backend (API y herramientas locales)

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.research.txt
```

`requirements.research.txt` incluye las dependencias de ejecución, de prueba y el lector local
de la API predictiva.

**Entorno exacto (recomendado para reproducir resultados).** `backend/requirements.lock.txt` fija
la versión de cada paquete del entorno con el que se probó (incluidas las dependencias
indirectas), generado con `pip freeze` sobre CPython 3.12 en Windows x64:

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
.\backend\.venv\Scripts\python.exe -m pip check
```

Con un entorno nuevo, `pip freeze` debe coincidir con el archivo (sin contar sus comentarios).
`colorama`, `httptools`, `watchfiles` y `websockets` dependen de la plataforma: en otro sistema
operativo conviene instalar `requirements.research.txt` y comparar. Al cambiar las dependencias, se
actualiza `requirements.research.txt` (o los que incluye), se instala en un venv nuevo, se corre la
regresión del backend y se regenera el archivo con
`.\backend\.venv\Scripts\python.exe -m pip freeze`, conservando el encabezado.

### 2.3 Paquete ML (preparación offline, sin entrenamiento al navegar)

```powershell
python -m venv ml/venv
.\ml\venv\Scripts\python.exe -m pip install -r ml/requirements.txt
.\ml\venv\Scripts\python.exe -m pip install -e "ml[database]"   # sólo si se usa la base de investigación
```

## 3. Configuración sin secretos

- La API pública lee su configuración de variables de entorno o de un `.env` **no versionado**.
  `.env.example` es la plantilla del despliegue con Docker Compose: tiene nombres con prefijo
  `SIGARD_` y valores de ejemplo («reemplazar-por-…») que hay que cambiar. Nunca contiene
  secretos reales.
- Variables principales de la API (`backend/app/config.py`):

  | Variable | Uso |
  |---|---|
  | `SECRET_KEY` | Obligatoria. Aleatoria, ≥ 32 caracteres. Firma las sesiones |
  | `DATABASE_URL` | Base de la API (SQLite local o PostgreSQL/PostGIS gestionado) |
  | `CORS_ORIGINS` | Orígenes permitidos separados por coma, sin comodines |
  | `AUTO_CREATE_SCHEMA` | `true` sólo en desarrollo con base vacía; en producción se usan migraciones |
  | `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` | Crean la **primera** cuenta si la tabla está vacía. Retirarlas después |
  | `REPORT_RETENTION_DAYS` | Retención de reportes (180 por defecto) |
  | `SIGARD_PUBLIC_ACTIVITY` | Sólo el valor `fixture` cambia algo: sirve el paquete **ficticio** |

- Para generar una clave aleatoria sin escribirla en ningún archivo:

  ```powershell
  $env:SECRET_KEY = -join ((48..57)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
  ```

- Las credenciales de la base de investigación las genera `tools/epidemiology_local.py init` en
  archivos privados ignorados por Git. Nunca se copian URLs con contraseña a la terminal ni a
  documentos.

## 4. Base de investigación PostgreSQL/PostGIS (puerto 55439)

Sólo hace falta para cargar entregas nuevas o regenerar paquetes desde la base. La API pública
y las demostraciones no la usan.

```powershell
# Una única vez, en una distribución WSL sin clústeres previos (requiere root):
wsl.exe -d Ubuntu -u root -- bash /mnt/c/RUTA/AL/REPO/backend/database/epidemiology/install-wsl-packages.sh
.\ml\venv\Scripts\python.exe -B tools/epidemiology_local.py init     # crea el clúster y las credenciales privadas

# Uso habitual:
.\ml\venv\Scripts\python.exe -B tools/epidemiology_local.py start
.\ml\venv\Scripts\python.exe -B tools/epidemiology_local.py status
.\ml\venv\Scripts\python.exe -B tools/epidemiology_local.py stop     # conserva los datos
```

- `init` crea `sigard_epi_local_v1` y `sigard_epi_test_v1` en un clúster propio, sin servicio
  permanente. **No usar `init` para reiniciar ni borrar.**
- Encender el clúster sólo para la operación que lo necesita y apagarlo al terminar.
- Migraciones privadas: `--migrate` del importador (ver §7). Usan
  `backend/alembic-epidemiology.ini` y no tocan la base de la API.

## 5. Ejecutar el sistema

| Comando | Qué levanta | Puertos | Requisitos |
|---|---|---|---|
| `npm.cmd --prefix frontend run dev:demo` | Sitio completo con API **ficticia**, SQLite temporal y cuenta generada | 5173 · 8766 | Ninguno privado |
| `npm.cmd --prefix frontend run dev` | Entorno de trabajo: sitio con el **visor predictivo** en Administración (`/admin/predictivo`, con sesión de administrador) y la **Administración completa** (login, reportes, contenido preventivo, cuentas, alertas internas y auditoría) con SQLite privado persistente, todo en la API administrativa 8767 | 5173 · 8767 | Paquetes privados instalados (§8); para ingresar a Administración, una cuenta local (§6) |
| `npm.cmd --prefix frontend run dev:alerts` | **Obsoleto**: alias de `dev` (avisa al iniciar) | Igual que `dev` | Igual que `dev` |

- Abrir siempre `http://127.0.0.1:5173/`.
- **Ctrl+C** cierra sólo lo que inició el comando. En `dev:demo` también elimina la base temporal
  y la cuenta.
- Antes de cambiar de entorno, detener el anterior. Para comprobar que los puertos estén libres:

  ```powershell
  Get-NetTCPConnection -LocalPort 5173,5174,8000,8766,8767 -State Listen -ErrorAction SilentlyContinue
  ```

- El visor arranca siempre en **modo protegido**. El selector de valores exactos sólo existe si
  `dev` se inicia con `SIGARD_PRIVATE_VIEW=1` y nunca se usa en demostraciones.
- `dev` arranca aunque no exista la cuenta de administrador local: el login se rechaza hasta
  crearla y la terminal muestra el comando de §6. No crea cuentas ni muestra contraseñas.
- El SQLite privado de la Administración local está en `data/interim/official/internal-alerts-v1/`
  (ignorado por Git) y conserva reportes, contenido, cuentas y alertas entre sesiones.
- La API administrativa precarga las predicciones para las alertas durante unos 25 s.

### 5.1 Vista «Actividad registrada» ficticia (opcional)

La API administrativa de `dev` (8767) también atiende las rutas públicas. Para ver la vista con el
paquete **ficticio** generado, iniciar `dev` con la opción explícita:

```powershell
$env:SIGARD_PUBLIC_ACTIVITY = 'fixture'
npm.cmd --prefix frontend run dev
Remove-Item Env:SIGARD_PUBLIC_ACTIVITY   # al terminar
```

Sin esa variable la vista queda oculta. Es la única opción que `dev` toma del entorno para la API
administrativa: no lee `.env`, `DATABASE_URL` ni secretos.

## 6. Cuenta de administrador

| Entorno | Cómo se obtiene |
|---|---|
| `dev:demo` | Se genera en cada arranque y se muestra **una sola vez** en la terminal. No se guarda |
| `dev` | Se crea una vez, en otra terminal y en forma interactiva (la contraseña no se muestra): `.\backend\.venv\Scripts\python.exe -B backend/app/alerts_local.py create-admin`. Puede crearse con `dev` en marcha, sin reiniciarlo |
| API desplegada | `ADMIN_BOOTSTRAP_EMAIL` y `ADMIN_BOOTSTRAP_PASSWORD` crean la primera cuenta sólo con la tabla vacía. Después se retiran del entorno, y las demás cuentas se crean desde **Gestionar cuentas** |

Usar correos de función (por ejemplo `aceptacion@example.test` en pruebas) y entregar las
contraseñas por un medio seguro. Si se pierde el acceso a todas las cuentas, no hay recuperación
anónima: interviene el operador autorizado.

## 7. Cargar una nueva entrega de datos

Una entrega nueva **no reentrena ningún modelo**: los modelos y artefactos están congelados.
Usarla para entrenar o evaluar exige una campaña nueva, autorizada y prerregistrada.

Con el clúster encendido y la conexión cargada desde el archivo privado (sin imprimirla):

```powershell
$epiConfig = Get-Content -Raw -LiteralPath data/interim/official/database-local-v1/connection.private.json | ConvertFrom-Json
$env:SIGARD_EPI_DATABASE_URL = $epiConfig.url

# 1. Migrar el esquema privado (idempotente)
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_import --migrate --report data/interim/official/NUEVA_ENTREGA/migration.private.json
# 2. Inventario sin escribir en la base
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_import --dry-run --report data/interim/official/NUEVA_ENTREGA/inventory.private.json
# 3. El responsable aprueba un JSON privado con el SHA-256 de cada archivo; luego se importa y valida
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_import --apply --authorization data/interim/official/NUEVA_ENTREGA/authorization.private.json --report data/interim/official/NUEVA_ENTREGA/import.private.json
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_import --validate --report data/interim/official/NUEVA_ENTREGA/validation.private.json
# 4. Analítica y consolidación en versiones nuevas (nunca sobrescriben)
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_analytics --config data/interim/official/NUEVA_ENTREGA/analytics-config.private.json --report data/interim/official/NUEVA_ENTREGA/analytics.private.json
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.consolidation prepare --connection CONEXION_PRIVADA --config CONFIG_PRIVADA --report INFORME_NUEVO_PRIVADO
```

- Los archivos fuente en `data/raw/` y en la carpeta de datos oficiales **no se modifican nunca**.
- Reimportar los mismos bytes no duplica registros. Un archivo cambiado crea un lote nuevo.
- Detalle de cada paso y de sus contratos JSON: [guía de importación](../database/import-guide.md)
  y [consolidación](../database/consolidation-stage1.md).

## 8. Generar los paquetes offline

Todos los paquetes se escriben en carpetas **nuevas** bajo `data/interim/official/` o
`data/processed/official/`, que Git ignora, y **nunca sobrescriben** uno existente. Ninguno
entrena ni infiere: proyectan resultados ya congelados y fijan cada archivo con su SHA-256.

| Paquete | Cómo se genera | Lo usa |
|---|---|---|
| Backtest histórico (referencia) | `.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.backtest_bundle --connection … --config … --output …` ([etapa 3](../database/historical-backtesting-stage3.md)) | API de investigación |
| Candidatos ML v2 | `compile_bundle(root, carpeta_de_campaña, lector_de_referencia, destino_nuevo)` de `sigard_ml.forecasting.predictive_ml_bundle_v2` (ver abajo) | Visor y alertas |
| Historia anual precalculada | `cd backend; .\.venv\Scripts\python.exe -B -m app.predictive_history build` | Visor (`/history`) |
| Actividad registrada | `sigard_ml.publication.activity_package fixture` (ficticio) o `build` (real, sólo con pedido expreso) | API pública |

**Candidatos ML v2.** Se compila con un script privado, desde la raíz:

```python
import hashlib, json, sys
from pathlib import Path
root = Path.cwd(); sys.path.insert(0, str(root / 'backend'))
from app.predictive_service import SnapshotReader
from sigard_ml.forecasting.predictive_ml_bundle_v2 import compile_bundle
registry = Path('data/interim/official/historical-backtest-session-v1/registry.private.json')
reader = SnapshotReader(registry, hashlib.sha256((root / registry).read_bytes()).hexdigest(), root=root)
destino = root / 'data/interim/official/<carpeta-nueva>'
result = compile_bundle(root, root / 'data/interim/official/corrective-v2-20261112-v1', reader, destino / 'bundle-v2')
(destino / 'registry.private.json').write_text(json.dumps(result, indent=2))
```

Antes de escribir, la compilación verifica el protocolo congelado, los 48 artefactos y las
53 248 predicciones, y exige reproducir las métricas congeladas.

**Historia anual precalculada.** Se reconstruye después de cualquier cambio en el backtest, en los
candidatos o en el código del servicio, porque la API la bloquea (503) si sus entradas cambiaron:

```powershell
cd backend
.\.venv\Scripts\python.exe -B -m app.predictive_history build    # falla si la carpeta ya existe: renombrar o borrar la anterior
.\.venv\Scripts\python.exe -B -m app.predictive_history verify   # debe informar 14 historias idénticas
cd ..
```

**Actividad registrada.**

```powershell
$env:PYTHONPATH='ml/src'
.\ml\venv\Scripts\python.exe -B -m sigard_ml.publication.activity_package fixture --output ml/.tmp/activity-fixture
# Real: SÓLO con pedido expreso del responsable; la API lo sirve únicamente con la autorización institucional
.\ml\venv\Scripts\python.exe -B -m sigard_ml.publication.activity_package build --connection <conexion>.private.json --config <config>.private.json --output data/processed/official/public-activity-v1
```

Ninguna variable de entorno habilita los datos reales. Hace falta el archivo privado de
autorización con el SHA-256 del manifiesto ([detalle](../actividad-registrada-publica.md)).

### 8.1 Verificar los hashes de un paquete

Cada paquete tiene un manifiesto con el SHA-256 de cada archivo. La API lo verifica en cada
lectura, y también puede comprobarse a mano:

```powershell
# Historia precalculada: cada archivo contra el manifiesto
$dir = 'data/interim/official/predictive-history-v1'
$m = Get-Content -Raw "$dir/manifest.private.json" | ConvertFrom-Json
$m.files.PSObject.Properties | ForEach-Object {
  $real = (Get-FileHash -Algorithm SHA256 (Join-Path $dir $_.Name)).Hash.ToLower()
  '{0}  {1}' -f ($(if ($real -eq $_.Value) {'OK   '} else {'FALLA'})), $_.Name
}
# El manifiesto contra su registro
$r = Get-Content -Raw "$dir/registry.private.json" | ConvertFrom-Json
(Get-FileHash -Algorithm SHA256 "$dir/manifest.private.json").Hash.ToLower() -eq $r.sha256
```

El mismo patrón sirve para `data/processed/official/public-activity-v1/manifest.json`, que
tiene la clave `files`. Un archivo alterado bloquea la respuesta correspondiente: el visor muestra
que el paquete no pudo verificarse, y la actividad responde 404.

## 9. Correr las pruebas

```powershell
# Frontend
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run test:security
npm.cmd --prefix frontend run test:dev
npm.cmd --prefix frontend run test:backtest
npm.cmd --prefix frontend run test:research
npm.cmd --prefix frontend run test:public-map
npm.cmd --prefix frontend run test:public-activity
npm.cmd --prefix frontend run test:read-retry
npm.cmd --prefix frontend run test:citizen
npm.cmd --prefix frontend run test:prevention
npm.cmd --prefix frontend run test:alerts
npm.cmd --prefix frontend run test:demo

# Backend aislado (sin .env ni PostgreSQL)
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py --backend-regression

# ML: pruebas ficticias seleccionadas, sin entrenamiento ni fuentes privadas
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_public_activity_package.py ml/tests/test_backtest_bundle.py ml/tests/test_predictive_ml_bundle_v2.py -p no:cacheprovider

# Seguridad del repositorio
.\backend\.venv\Scripts\python.exe -B tools/check_repository_security.py
git diff --check
```

**Pruebas de navegador.** Usan el Puppeteer del proyecto (§2.1). `$env:SIGARD_BROWSER_MODULE` sigue
sirviendo para usar otra instalación (ruta al paquete `puppeteer`).

| Prueba | Requisito previo |
|---|---|
| `test:predictive:browser`, `test:public-activity:browser`, `test:accounts:browser` | `dev` en marcha (las dos últimas redirigen 8000 y 8767 a su propia API ficticia) |
| `test:citizen:browser`, `test:prevention:browser`, `test:alerts:browser`, `test:demo:browser` | Levantan su propio entorno; los puertos deben estar libres |
| `test:performance` (`-- --target production` para el bundle de producción) | Levanta sus entornos. Tarda unos 20 minutos por modo |

**Migraciones en PostGIS real.** `backend/tests/postgres_migration_check.py` crea una base
descartable en el clúster 55439, recorre la cadena completa y la elimina al terminar. Las 6
pruebas PostGIS omitidas usan un contenedor Docker descartable propio (`backend/tests/postgis_disposable.py`,
127.0.0.1:5435), no la base de investigación; quedan omitidas por la regla de no iniciar Docker.

## 10. Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| «El puerto 127.0.0.1:5173 está ocupado» | Otro entorno sigue abierto | Cerrarlo con Ctrl+C. No se detienen procesos ajenos |
| El visor dice que el paquete no pudo verificarse | Un archivo privado cambió o falta, o la historia quedó desactualizada | Verificar hashes (§8.1) y reconstruir la historia |
| «Actividad registrada» no aparece | Sin autorización o sin la API pública | Es el comportamiento esperado |
| Error de `SECRET_KEY` al iniciar la API | Clave ausente o menor a 32 caracteres | Definirla en el entorno (§3) |
| Las alertas internas tardan en responder al iniciar `dev` | Precarga de predicciones | Esperar unos 25 s |
| «Credenciales inválidas» en Administración con `dev` | Todavía no hay cuenta local | Crearla con el comando de §6 (la terminal de `dev` lo muestra) |
