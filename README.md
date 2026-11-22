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

## Inicio rápido (Windows, desde la raíz)

```powershell
npm.cmd --prefix frontend ci
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.research.txt
npm.cmd --prefix frontend run dev:demo      # demostración ficticia completa → http://127.0.0.1:5173/
```

| Comando | Para qué | Requiere datos privados |
|---|---|---|
| `npm.cmd --prefix frontend run dev:demo` | Sitio completo con API ficticia y SQLite temporal | No |
| `npm.cmd --prefix frontend run dev` | Entorno de trabajo: visor predictivo (8765) y Administración completa (8767: login, reportes, contenido, cuentas y alertas) con SQLite privado persistente | Sí |
| `npm.cmd --prefix frontend run dev:alerts` | **Obsoleto**: alias de `dev` | Sí |

`dev` arranca aunque todavía no exista la cuenta de administrador local y muestra en la terminal el
comando para crearla. `dev` y `dev:demo` usan el puerto 5173: **no se ejecutan en paralelo**. La instalación completa, la
configuración, la base de investigación, la carga de datos, los paquetes y las pruebas están en
el [manual de instalación](docs/manuales/manual-instalacion.md).

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
