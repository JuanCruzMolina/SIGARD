# SIGARD

**Sistema de vigilancia territorial del dengue para La Rioja Capital.** Prototipo académico de la
Universidad Nacional de La Rioja (Ingeniería en Sistemas de Información).

SIGARD integra en un sitio:
- información de prevención y reportes ciudadanos anónimos;
- una vista pública de actividad histórica protegida por zona;
- un visor predictivo experimental por radio censal y semana;
- alertas internas con aprobación humana;
- la administración de cuentas y contenidos.

Es un **prototipo en evaluación**: no es un sistema operativo de vigilancia ni reemplaza las
indicaciones sanitarias oficiales.

Versión vigente: **`v0.9.1-aceptacion`** (rama `entrenamiento-ML`, noviembre de 2026).

> **Contenido del repositorio.** Código, pruebas, fixtures ficticias, mapas públicos aprobados y
> documentación. **No incluye** fuentes sanitarias, datos procesados, modelos entrenados,
> predicciones, credenciales ni autorizaciones: viven en carpetas privadas ignoradas por Git.

## Estado del proyecto

### Módulos

| Módulo | Estado |
|---|---|
| 1. Ingesta y procesamiento | Importador por hash, consolidación radio × semana. Completo para uso local y experimental |
| 2. Modelo predictivo | Visor retrospectivo 2021–2024 con referencia estadística y candidatos ML **no promovidos** |
| 3. Geolocalización y visualización | Mapa de contexto. «Actividad registrada» con supresión y desactivada hasta la autorización del Ministerio |
| 4. Alertas | Alertas **internas** con aprobación humana. Publicación ciudadana bloqueada |
| 5. Usuarios y roles | Rol `admin` con JWT, revocación de sesiones y auditoría. Ciudadanía anónima |
| 6. Información sanitaria | Contenido preventivo editable con versiones, publicación y auditoría |

### Criterios de aceptación del anteproyecto

| Criterio | Estado |
|---|---|
| (a) Módulos operativos en un entorno de prueba | **Cumple** |
| (b) Modelo superior a un baseline | **Cumple para cantidad**: −13,6 % de MAE frente a la persistencia. Presencia empata |
| (c) Respuesta < 5 s | **Cumple en producción**: 6/6 operaciones con 1 y 5 usuarios |
| (d) Aceptación con dos referentes del Ministerio | **Pendiente** de las sesiones (kit listo) |

Detalle, evidencia, defectos y pendientes: [verificación final](docs/verificacion-final.md).

**Pendientes principales:**
- sesiones de aceptación con el Ministerio;
- autorización institucional para publicar «Actividad registrada» con datos reales;
- tarea programada de retención en un despliegue institucional;
- 6 pruebas PostGIS que exigen Docker (no se inicia por regla del proyecto).

## Instalación (Windows, desde la raíz)

Requisitos: Git, Node.js 24 (probado con 24.15.0) y Python 3.12. No hace falta Docker ni
PostgreSQL para el sitio ni para la demostración.

```powershell
# 1. Frontend (instala también Puppeteer 25.9.0, sólo para las pruebas de navegador)
npm.cmd --prefix frontend ci

# 2. Backend con las versiones exactas con las que se probó (recomendado)
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
.\backend\.venv\Scripts\python.exe -m pip check
```

- **Lock del backend.** `backend/requirements.lock.txt` fija cada paquete (incluidas las
  dependencias indirectas) del entorno probado en CPython 3.12 / Windows x64. En otro sistema
  operativo, instalar `backend/requirements.research.txt` (rangos de versiones) y comparar.
- **Puppeteer.** `npm ci` descarga Chrome for Testing 152 en `%USERPROFILE%\.cache\puppeteer\`
  (≈700 MB, fuera del repositorio). Sin conexión o detrás de un proxy:
  `$env:PUPPETEER_SKIP_DOWNLOAD='true'` antes de `npm ci` y después
  `node frontend/node_modules/puppeteer/lib/puppeteer/node/cli.js browsers install chrome`.
  No llega al sitio publicado.

Detalle (configuración, base de investigación, carga de datos, paquetes offline y pruebas):
[manual de instalación](docs/manuales/manual-instalacion.md).

## Levantar todo

```powershell
npm.cmd --prefix frontend run dev        # entorno de trabajo → http://127.0.0.1:5173/
npm.cmd --prefix frontend run dev:demo   # demostración ficticia descartable → http://127.0.0.1:5173/
```

| Comando | Qué levanta | Requiere datos privados |
|---|---|---|
| `run dev` | Vite + la API administrativa local: sitio público, Administración completa con SQLite privado persistente y visor predictivo con sesión de administrador | Sí, para el visor (paquetes offline instalados). Sin ellos arranca igual y el visor responde 503 |
| `run dev:demo` | Vite + API ficticia con SQLite temporal y una cuenta generada por sesión (se muestra una vez en la terminal). **Ctrl+C** borra todo | No |
| `run dev:alerts` | **Obsoleto**: alias de `dev` | Sí |

`dev` y `dev:demo` comparten el puerto 5173: **no se ejecutan a la vez**. **Ctrl+C** cierra sólo
los procesos que inició el comando; si un puerto está ocupado, el inicio se detiene con un mensaje
(no se detienen procesos ajenos).

### Puertos

| Puerto (sólo `127.0.0.1`) | Qué atiende | Quién lo usa |
|---|---|---|
| 5173 | Sitio React/Vite | `dev`, `dev:demo` y las pruebas de navegador |
| 8767 | API administrativa local (`backend/app/alerts_local.py serve`): login, reportes, contenido, cuentas, alertas, auditoría, visor predictivo y rutas públicas | `dev` |
| 8766 | API ficticia de la demostración (SQLite temporal) | `dev:demo` y algunas pruebas |
| 5174 | Vite propio de las pruebas de reportes, cuentas y ciudadanía | Pruebas de navegador |
| 8000 | API pública FastAPI (`VITE_API_URL` en `frontend/.env`) | Modo habitual / producción; no la inicia `dev` |
| 55439 | Base de investigación PostgreSQL/PostGIS (WSL, manual) | Preparación de datos y ML; nunca el navegador |

El puerto 8765 (antiguo lector A/B sin autenticación) no se usa desde F2.

## Entrar a Administración

1. Con `dev` en marcha, crear **una sola vez** la cuenta local, en otra terminal (la contraseña se
   pide sin mostrarla; puede hacerse con `dev` funcionando):
   `.\backend\.venv\Scripts\python.exe -B backend/app/alerts_local.py create-admin`.
   En `dev:demo` no hace falta: usar el correo y la contraseña que muestra la terminal, sin
   guardarlos.
2. Abrir `http://127.0.0.1:5173/admin` (o **Administración** en el menú superior) e ingresar.
3. La sesión dura 60 minutos; **Cerrar sesión** está en la barra superior.

El menú lateral tiene siete secciones:

| Sección | Ruta | Qué muestra |
|---|---|---|
| **Inicio** | `/admin/inicio` | Lo que requiere una decisión (alertas pendientes, reportes «Recibido», contenido sin publicar), estado del sistema, los 10 pendientes más antiguos y accesos rápidos |
| **Módulo predictivo** | `/admin/predictivo` | Reconstrucción 2021–2024 por radio censal y semana: ¿Dónde? (top-10) y ¿Cuántos?, modelo ML no promovido frente al método de referencia, panel por radio y desempeño por año. Siempre en modo protegido (< 5 oculto). Sólo con `dev` |
| **Alertas internas** | `/admin/alertas` | Reglas con su frecuencia histórica, evaluación manual de una semana, candidatas para aprobar o descartar con motivo, e historial. Nada se publica a la ciudadanía |
| **Reportes ciudadanos** | `/admin/reportes` | Bandeja de reportes anónimos con filtros, detalle protegido (ubicación exacta), cambio de estado, mensaje público, nota interna y exportación CSV |
| **Contenido preventivo** | `/admin/contenido` | Editor de las secciones de «Prevención y ayuda» con vista previa, borrador, publicación con versión, despublicación e historial |
| **Cuentas** | `/admin/cuentas` | Alta, rotación de contraseña y desactivación de cuentas, siempre con la contraseña de quien autoriza; la última cuenta activa no se puede desactivar |
| **Auditoría** | `/admin/auditoria` | Registro de sólo lectura de quién hizo qué y cuándo, con filtros en la dirección; nunca muestra contraseñas, textos ni valores del visor. Sólo con `dev` |

Uso detallado: [manual del administrador](docs/manuales/manual-administrador.md).

## Documentación

### Manuales
- [Manual para la ciudadanía](docs/manuales/manual-ciudadano.md): prevención, reportes, seguimiento, actividad registrada y privacidad.
- [Manual del administrador](docs/manuales/manual-administrador.md): cuentas, reportes, contenido preventivo, visor predictivo, alertas y buenas prácticas.
- [Manual de instalación y operación técnica](docs/manuales/manual-instalacion.md): entornos, configuración, ejecución, datos, paquetes y pruebas.

### Documentación técnica
- [Arquitectura](docs/tecnica/arquitectura.md): diagramas de contexto y lógico, componentes, seguridad.
- [Modelo de datos](docs/tecnica/modelo-datos.md): entidad-relación de ambas bases, generado desde las migraciones (`tools/generate_erd.py`).
- [Registro de decisiones técnicas (ADR)](docs/tecnica/decisiones.md).
- [Módulo predictivo integrado](docs/predictive-module-final.md): fuentes, candidatos, endpoints, historia precalculada y límites.
- [Actividad registrada](docs/actividad-registrada-publica.md): parámetros de protección, supresión, autorización.
- [Alertas internas](docs/alertas-internas.md): especificación, reglas, privacidad y arquitectura.
- [API y backend](backend/README.md) · [Frontend](frontend/README.md) · [Política del directorio de datos](data/README.md).
- [Seguridad del repositorio](docs/repository-security.md) · [Distribución y demostración](docs/publication-and-demo.md).

### Verificación y aceptación
- [Verificación final (P6/P6.1)](docs/verificacion-final.md): matriz de trazabilidad, criterios, rendimiento, seguridad, defectos.
- Kit de aceptación: [protocolo](docs/aceptacion/protocolo.md), [escenarios](docs/aceptacion/escenarios.md), [criterios](docs/aceptacion/criterios.md), [cuestionario SUS](docs/aceptacion/cuestionario-sus.md), [preparación de la sesión](docs/aceptacion/preparacion-sesion.md), [acta modelo](docs/aceptacion/acta-modelo.md) y [planilla de resultados](docs/aceptacion/planilla-resultados.csv).
- [Cierre funcional para la tesis](docs/cierre-funcional-tesis.md) · [Protocolo de validación predictiva](docs/validacion-predictiva-tesis.md) · [Consolidación técnica de las etapas 1 a 17](docs/technical-consolidation.md).

### Base de investigación y ML (`docs/database/`)
- [Arquitectura de la base privada](docs/database/architecture.md), [diagramas](docs/database/erd.md), [diccionario](docs/database/data-dictionary.md), [normalización](docs/database/normalization.md).
- [Instalación e importación](docs/database/import-guide.md), [resoluciones](docs/database/resolution-guide.md), [consolidación etapa 1](docs/database/consolidation-stage1.md), [Censo 2022](docs/database/census-2022-integration.md).
- [Motor predictivo etapa 2](docs/database/predictive-motor-stage2.md), [backtesting etapa 3](docs/database/historical-backtesting-stage3.md), [cierre de candidatos ML](docs/database/ml-candidates-closure.md).
- [Componente predictivo](docs/database/predictive-core.md), [ingesta predictiva](docs/database/predictive-ingestion.md), [migración de ML a PostGIS](docs/database/postgres-ml-migration.md), [lectura A/B/V3](docs/database/ml-integration.md), [investigación con política B](docs/database/option-b-research.md).

### Contratos epidemiológicos y de datos
- [Contrato de clasificación, episodios y cobertura](docs/epidemiological-labeling-and-coverage-contract.md) · [auditoría de calidad](docs/epidemiological-data-quality-audit.md).
- [Calendario epidemiológico 2020–2026](docs/official-calendar.md) · [límite censal de la ciudad](docs/principal-city-boundary.md).
- [Contrato de entrada de conteos t+1](docs/principal-count-input-contract.md) · [módulo principal de conteos](docs/principal-count-forecasting.md).

### Histórico (etapas anteriores, se conservan como registro)
- **v0.1:** [arquitectura](docs/architecture.md), [contrato de datos](docs/data-contract.md), [metodología](docs/methodology.md), [datos sintéticos](docs/synthetic-data.md), [funcionalidades](docs/mvp-funcionalidades.md) y [estado del MVP](docs/mvp-functional-status.md), [plan del proyecto](docs/plan-proyecto.md), [iteración 11](docs/iteration-11-public-api.md), [Docker](docs/docker-development.md).
- **Fases oficiales 1–5:** [pipeline](docs/official-pipeline.md), [ingestión](docs/official-ingestion.md), [geografía](docs/official-geography.md), [panel observado](docs/official-observed-panel.md), [recuperación temporal](docs/official-date-recovery.md), [cobertura](docs/official-coverage.md), [universo](docs/official-universe.md), [escenario asumido](docs/official-assumed-scenario.md), [revisión epidemiológica](docs/official-epidemiology-review.md), [conciliación](docs/official-selection-reconciliation.md), [preparación espacial](docs/official-spatial-ml.md), [experimento](docs/official-spatial-experiment.md), [investigación](docs/official-spatial-research.md), [diagnóstico](docs/official-spatial-diagnostics.md), [viabilidad temporal](docs/official-temporal-feasibility.md), [modelo B](docs/official-spatial-model-b.md), [robustez](docs/official-spatial-robustness.md).
- **A/B, V3 y exploraciones:** [contrato A/B](docs/experimental-spatial-results-contract.md), [inicio local A/B](docs/experimental-spatial-local.md), [consulta por fecha](docs/experimental-spatial-date-query.md), [entrenamiento histórico](docs/historical-training-experimental.md), [preparación del entrenamiento](docs/next-ml-training-readiness.md), [diagnóstico V3](docs/diagnostico-predictivo-v3.md), [evaluación independiente V3](docs/evaluacion-independiente-v3.md), [viabilidad territorial](docs/viabilidad-prediccion-territorial.md), [demo predictiva privada](docs/predictive-experimental-demo.md), [resumen del desarrollo](docs/SIGARD-resumen-desarrollo.md).

## Arquitectura en una línea

React/Vite/Leaflet (Vercel) → FastAPI + PostgreSQL/PostGIS (API pública). En el equipo local se
suman la API predictiva de sólo lectura, que sirve paquetes offline verificados por SHA-256, y la
base de investigación separada (PostGIS, puerto 55439). Ver
[arquitectura](docs/tecnica/arquitectura.md).

## Reglas del repositorio

- `data/raw/` y las fuentes oficiales son inmutables.
- No se versionan datos, modelos, predicciones, credenciales, `.env` ni archivos `*.private.*`.
- Los procesos aleatorios usan semillas explícitas. La evaluación es temporal (walk-forward con
  purga), nunca con particiones aleatorias de filas.
- Nada se entrena ni se infiere al navegar. Los artefactos congelados no se recalculan sin una
  autorización específica.
- Toda salida derivada de datos epidemiológicos protege los valores menores a 5.
- Docker Desktop permanece apagado. No se usa el PostgreSQL de `127.0.0.1:5432`.
- Instrucciones completas para quien contribuye: [AGENTS.md](AGENTS.md).

## Autores

- Dominguez Sotomayor, Santiago Ismael
- Molina Leguiza, Juan Cruz

Universidad Nacional de La Rioja — Ingeniería en Sistemas de Información.
