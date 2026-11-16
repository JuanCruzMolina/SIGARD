# Verificación final antes de las pruebas de aceptación (P6)

Fecha: 16/11/2026 · Rama `entrenamiento-ML` · Etiqueta `v0.9.0-aceptacion`.

Estados usados: **Cumple** (implementado y verificado con la prueba citada) · **Parcial** (cumple con
límites declarados) · **Distinto** (se resolvió de otra forma que lo prometido, con justificación) ·
**Pendiente** (no cubierto).

> El texto original del anteproyecto no está en el repositorio: `PRODUCT.md` cita una ruta de otro
> equipo. La matriz parte de `PRODUCT.md`, `docs/plan-proyecto.md`, el punto 13 del tutor y las
> consignas de esta etapa. Los criterios (a), (b) y (d) se registran como **pendientes de
> transcripción literal**, para no atribuirles un contenido inventado.

## 1. Módulos del anteproyecto

| Módulo | Especificación | Implementación | Prueba | Evidencia | Estado |
|---|---|---|---|---|---|
| 1. Ingesta y procesamiento | Carga, limpieza y procesamiento de registros epidemiológicos | Importador SISA por hash (`ml/src/sigard_ml/ingestion/epidemiology/`), consolidación etapa 1 (`forecasting/consolidation.py`), importador público y lote ficticio editable en la demo | `ml/tests/test_epidemiology_database.py`, `test_consolidation.py`, `backend/tests/test_publication_import.py` | Regresión backend e importador; consolidación documentada en `docs/database/consolidation-stage1.md` | **Parcial**: completo para el uso local y experimental; sin flujo institucional de carga en línea |
| 2. Modelo predictivo | Predicción por radio censal y semana | Visor histórico h=1 con referencia estadística y candidatos ML no promovidos (`predictive_service.py`, `HistoricalBacktest.jsx`) | `test_predictive_service.py`, `test_predictive_ml.py`, `npm run test:backtest`, `test:predictive:browser` | §6 (suite) | **Parcial**: reconstrucción retrospectiva; ningún modelo ML promovido; 2025–2026 bloqueados |
| 3. Geolocalización y visualización | Mapa ciudadano agregado («mapa de calor») | Mapa público de contexto y simulación; vista **«Actividad registrada»** con niveles por radio, supresión primaria y complementaria, desactivada sin autorización (`public_activity.py`, `PublicActivity.jsx`) | `test_public_activity.py`, `test_public_activity_package.py`, `npm run test:public-activity`, `test:public-activity:browser` | `docs/actividad-registrada-publica.md`; paquete real con 0 revelaciones (P4.1) | **Distinto**: niveles por radio con supresión en lugar de mapa de calor kernel (ver §5) |
| 4. Alertas | Alertas configurables | Reglas, evaluación semanal manual, candidatas con aprobación humana y auditoría; sin publicación ciudadana (`internal_alerts.py`) | `test_internal_alerts.py`, `npm run test:alerts`, `test:alerts:browser`; migración 06 y restricción en PostGIS (§2) | `docs/alertas-internas.md` | **Parcial**: avisos internos retrospectivos; sin correo/SMS ni alerta oficial |
| 5. Gestión de usuarios por roles | Acceso detallado sólo autenticado y autorizado | Rol `admin` con JWT HS256 versionado, alta/rotación/desactivación con confirmación, último administrador protegido | `test_admin_accounts.py`, `test_route_authorization.py`, `test:accounts:browser` (normal e integral) | §4 | **Cumple** (con la diferencia de §5: ciudadanía anónima) |
| 6. Información sanitaria administrable | Contenido preventivo editable | Borrador, publicación con versión, despublicación y auditoría (`prevention.py`); página pública desde la API con respaldo estático | `test_prevention_content.py`, `test:prevention`, `test:prevention:browser`; migración 05 y carga inicial en PostGIS (§2) | `backend/README.md` § módulo 6 | **Cumple** |

## 2. Criterios de evaluación

| Criterio | Especificación | Implementación / prueba | Evidencia | Estado |
|---|---|---|---|---|
| (a) | Pendiente de transcripción literal del anteproyecto | — | — | **Pendiente** |
| (b) | Pendiente de transcripción literal del anteproyecto | — | — | **Pendiente** |
| (c) Rendimiento | p95 < 5 s por operación, 1 y 5 usuarios, 30 repeticiones (punto 13 del tutor) | `frontend/scripts/performance.browser.mjs` (`npm run test:performance`) | §3 | **Parcial**: 11 de 12 mediciones cumplen; la carga del visor con 5 usuarios no cumple |
| (d) | Pendiente de transcripción literal del anteproyecto | — | — | **Pendiente** |

## 3. Rendimiento (criterio c)

**Script reproducible:** `frontend/scripts/performance.browser.mjs`. Se ejecuta con
`npm.cmd --prefix frontend run test:performance`; `--only a,b` repite operaciones y `--reps N` cambia
la cantidad de repeticiones. Levanta sus propios entornos y registra sólo tiempos en
`data/interim/official/performance-v1/` (privado).

**Entorno:**
- AMD Ryzen 5 5500 (12 hilos), 16 GB de RAM, Windows 11 (10.0.26300), Node 24.15.0, Chromium 152 headless.
- Todo en el mismo equipo: Vite **en modo desarrollo** (sin bundle de producción), APIs locales uvicorn de un solo proceso.
- Se excluyen las teselas de calles y las fuentes web externas, para que la red de Internet no influya.

**Volumen:**
- 263 radios oficiales en la geometría del visor.
- 208 semanas evaluables 2021–2024 (catálogo de 366 semanas).
- Visor y alertas con la API predictiva local en modo protegido.
- «Actividad registrada» con la fixture ficticia (24 celdas + 1 fuera del área, 45 bloques).

**Método:**
- 30 repeticiones con 1 usuario.
- 30 rondas con 5 usuarios concurrentes, cada uno en su propio contexto de navegador (150 muestras).
- p95 por rango más cercano.
- Las cargas se miden en frío: contexto nuevo por muestra, desde la navegación hasta el contenido completo.
- El cambio de semana y la consulta de radio se miden sobre un visor ya cargado, después de que terminaron sus cargas de fondo.
- Una muestra que supera 30 s se registra como falla (≥ 30 000 ms); nunca se descarta.

| Operación | Condición de fin | 1 usuario p95 | 5 usuarios p95 (máx.) | Umbral 5 s |
|---|---|---|---|---|
| Carga de «Actividad registrada» (fixture) | 25 polígonos y serie dibujados | 970 ms | 4 246 ms (4 444) | **Cumple** |
| Carga de prevención | 27 establecimientos y contenido de la API | 990 ms | 4 215 ms (4 270) | **Cumple** |
| Carga del visor | semana lista y ≥ 263 polígonos | 3 023 ms | **33 548 ms** (33 673; 48/150 muestras > 30 s) | **No cumple con 5 usuarios** |
| Cambio de semana (visor cargado) | semana nueva lista | 400 ms | 676 ms (698) | **Cumple** |
| Consulta de radio (visor cargado) | panel del radio | 184 ms | 370 ms (953) | **Cumple** |
| Panel de alertas | panel con semanas evaluables | 333 ms | 307 ms (320) | **Cumple** |

**Lectura del resultado:**
- La carga del visor **no cumple** el umbral con 5 usuarios concurrentes. La API predictiva local
  recalcula y vuelve a verificar la integridad de cada semana en cada pedido; esta decisión de diseño
  impide que un archivo alterado se sirva desde un caché. `/history` tarda unos 6,5 s por año con un
  usuario y unos 34 s con 5, porque las solicitudes se serializan en un solo proceso.
- Con un usuario, que es el uso previsto en las sesiones de aceptación (un participante a la vez),
  cumple holgadamente.
- La corrección posible es un caché por proceso indexado por los hashes ya verificados, o una
  historia precalculada en el bundle offline. Ambas modifican la política de integridad y quedan
  **pendientes de decisión**.
- Las cargas con 5 usuarios rondan 4,2 s porque Vite en modo desarrollo sirve los módulos sin
  empaquetar a 5 navegadores en frío a la vez. En producción (bundle estático) se espera menos, pero
  **no se midió**.
- La primera corrida midió el cambio de semana mientras el visor seguía cargando historias de fondo
  (p95 826 ms, con 1 muestra > 30 s). Se corrigió la preparación y se volvió a medir.
- El panel de alertas con 5 usuarios se midió en una corrida aparte, porque el límite de inicio de
  sesión (5 por 15 min) impedía 6 sesiones. Ahora se inicia una sola sesión y se reutiliza el token.

## 4. Medidas de seguridad prometidas

| Medida | Implementación | Prueba | Estado |
|---|---|---|---|
| Disociación de datos personales | Reportes ciudadanos anónimos; el seguimiento público expone sólo código, estado, fechas y mensaje; la ubicación exacta sólo está en el panel protegido; mapa público sólo agregado (radio completo, mínimo 5) | `test_citizen_reports.py::test_anonymous_report_and_public_status_do_not_expose_location`, `test_public_activity*.py`, `test:public-activity` (ausencia en `public`/`dist`) | **Cumple** |
| RBAC / JWT | `get_current_admin` en todas las rutas `/api/v1/admin/*` salvo el login; token con `exp`, `sub` y versión; superficie pública explícita | `test_route_authorization.py` (27 rutas administrativas protegidas; 401 sin token y con token falsificado en cada una), `test_admin_accounts.py` | **Cumple** |
| Auditoría | Auditoría de reportes (actualización, exportación y, desde P6, **consulta del detalle**), de cuentas (sin credenciales), de contenido preventivo (antes/después) y de alertas | `test_citizen_reports.py::test_admin_detail_view_is_audited_without_report_content`, `test_admin_accounts.py`, `test_prevention_content.py`, `test_internal_alerts.py` | **Cumple** (consulta de detalle corregida en P6) |
| Alta de administradores | Sólo un administrador autenticado crea cuentas, con su contraseña; sin registro público ni recuperación por correo; bootstrap sólo con base vacía | `test_admin_accounts.py`, `test:accounts:browser` | **Cumple** |
| Revocación de tokens | `token_version` en rotación y desactivación; sesión propia cerrada | `test_admin_accounts.py::test_rotation_revokes_every_old_token_and_password`, `test:accounts:browser` | **Cumple** |
| Retención | Reportes con `retention_until` (180 días por defecto) y purga diaria fuera del proceso web (`app/retention.py`) | `test_citizen_reports.py::test_retention_removes_only_expired_reports` | **Parcial**: la tarea programada de producción no está desplegada |
| Cabeceras y CSP | API: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `no-store` en admin; Vercel: CSP, Permissions-Policy, Referrer-Policy y X-Frame-Options | `test_admin_accounts.py`, `test:security`, revisión de `frontend/vercel.json` | **Cumple** (HSTS depende del dominio de despliegue) |
| Límites de entrada | Esquemas Pydantic con longitudes máximas, límites de frecuencia en reportes, geocodificación y login, CSV con neutralización de fórmulas | `test_citizen_reports.py`, `test_admin_accounts.py::test_password_confirmation_uses_existing_rate_limiter` | **Cumple** |
| Sin datos reales en el sitio público | Recursos públicos aprobados por hash; paquete de actividad sólo vía API autorizada; modo de valores exactos fuera del bundle | `test:security`, `test:public-activity`, `test:backtest` (`private-view.test.mjs`) | **Cumple** |

## 5. Diferencias con lo prometido (declaradas)

1. **Mapa de calor → niveles por radio con supresión.** Un kernel sobre registros georreferenciados
   permitiría inferir ubicaciones en zonas con pocos casos. Se publican categorías por radio censal
   completo en bloques de 4 semanas, con mínimo 5, supresión complementaria e informe de riesgo.
   Con datos reales, el 96,5 % de las celdas queda protegido (aporta información sobre todo en el
   brote de 2024).
2. **Capa por caso no implementada.** Por privacidad, ninguna vista (ni administrativa) muestra
   casos epidemiológicos individuales. La ubicación exacta sólo existe para reportes ciudadanos
   en el panel protegido.
3. **Ciudadanía anónima en lugar de un rol con cuenta.** El ciudadano consulta y reporta sin
   registrarse: minimiza los datos personales. El único rol con cuenta es `admin`.
4. **Alertas internas con aprobación humana**, no alertas automáticas a la población.
5. **Modelo predictivo retrospectivo**: no se promovió ningún candidato ML; la referencia
   estadística es la vista por defecto.

## 6. Resultados de la verificación P6

| Punto | Resultado | Evidencia |
|---|---|---|
| 1a. Modo privado del visor | El control de valores exactos aparece sólo con `SIGARD_PRIVATE_VIEW=1` en `dev`; el bundle de producción no lo contiene; la API no cambió | `private-view.test.mjs`, `dev.test.mjs`, `test:predictive:browser` en ambos modos |
| 1b. Modo integral de cuentas | Adaptado al módulo predictivo; 11/11 comprobaciones, 0 defectos | `SIGARD_INTEGRAL_REVIEW=1 SIGARD_EXPECT_STABLE=1 test:accounts:browser` |
| 1c. Falla intermitente de cuentas | Causa: `net::ERR_FAILED` al reescribir la URL con `request.continue` mientras otra solicitud interceptada se abortaba. Corregido con proxy desde Node | 0 fallas en 30 corridas (antes 1 cada 10–15); `browser-proxy.test.mjs` |
| 2. Migraciones en PostgreSQL 16.15 / PostGIS 3.4.2 | Base nueva `sigard_public_migration_test` en 55439: cadena completa, carga inicial de prevención (5 secciones, idempotente), bajada/subida de 05 y 06, candidata «publicada» rechazada (23514), umbral < 5 rechazado, API lista; base eliminada y clúster detenido | `backend/tests/postgres_migration_check.py` (11/11 pasos) |
| 2. Pruebas PostGIS omitidas (6) | **No ejecutadas**: requieren el runner descartable con Docker (puerto 5435, identidad propia); no se debilitaron sus guardas ni se inició Docker | — |
| 4. Rendimiento | 11 de 12 mediciones cumplen p95 < 5 s; la carga del visor con 5 usuarios no cumple | §3 |
| 5. Seguridad | 27 rutas administrativas exigen rol; 401 sin token o con token falso en todas; superficie pública explícita; auditoría de consulta de detalle agregada; auditoría del repositorio sin candidatos sensibles (197 controles) | `test_route_authorization.py`, `check_repository_security.py` |
| 5. Accesibilidad | Nombres accesibles, contraste AA de todo el texto visible y alcance por teclado en administración de prevención, alertas y actividad (1440 y 390 px) | `browser-a11y.mjs` en `test:prevention:browser`, `test:alerts:browser`, `test:public-activity:browser` |
| 6. Frontend | lint y build; `test:security` 15, `test:public-map` 5, `test:public-activity` 5, `test:research` 21, `test:dev` 21, `test:backtest` 22, `test:citizen` 4, `test:prevention` 5, `test:alerts` 5, `test:demo` 13: todo aprobado | — |
| 6. Backend | 360 aprobadas, 6 omitidas (PostGIS con Docker) | `publication_isolated.py --backend-regression` |
| 6. ML | 68 aprobadas (paquete público, bundles y exportaciones; sin entrenamiento ni fuentes privadas) | `pytest` de pruebas seleccionadas |
| 6. Navegador | cuentas (normal e integral), actividad, visor, ciudadano, prevención admin, alertas y demo integral: todo aprobado | — |

Límites:
- Sin lector de pantalla real ni dispositivo móvil físico.
- Rendimiento medido en modo desarrollo, no en producción.
- PostGIS verificado en el clúster local, no en un servidor institucional.

## 7. Defectos

### Corregidos en P6 (con regresión)

| Defecto | Causa | Corrección | Regresión |
|---|---|---|---|
| Consulta del detalle de un reporte (ubicación exacta) sin auditoría | Sólo se auditaban la actualización y la exportación | Se registra `view_detail` (sin contenido del reporte) | `test_admin_detail_view_is_audited_without_report_content` |
| Contraste insuficiente del texto atenuado (`--muted` 4,43:1 sobre el fondo del sitio; 4,04 sobre menta), incluidas las tablas de «Actividad registrada» | Color global demasiado claro | `--muted` pasa a #52676a (≥ 4,97:1 en todas las superficies claras) | `auditAccessibility` en las pruebas de navegador |
| La sonda de «Actividad registrada» podía quedar pendiente indefinidamente con una API ocupada; `dev:alerts` no terminaba de cargar la página | Sin tiempo límite en la solicitud (introducido en P4) | Tiempo límite de 5 s; falla cerrada (vista oculta) | `public-activity.test.mjs` (sonda colgada) y `test:alerts:browser` |
| Selector de valores exactos visible por defecto en el visor | Sin habilitación explícita | Visible sólo con `SIGARD_PRIVATE_VIEW=1` en desarrollo | `private-view.test.mjs` |
| Falla intermitente de `test:accounts:browser` | Reescritura de URL en la interceptación de Puppeteer | Proxy desde Node para las pruebas de navegador | `browser-proxy.test.mjs`, 30/30 |
| Carreras en `predictive.browser` y `public-activity.browser` | Lectura inmediatamente después del cambio de URL/ruta | Espera explícita del estado final | Corridas repetidas |
| `postgres_migration_check.py` escribía el resultado en la carpeta temporal | Ruta relativa resuelta después de cambiar de directorio | Rutas resueltas al inicio | Corrida final con evidencia |

### Pendientes

| Pendiente | Impacto | Propuesta |
|---|---|---|
| Carga del visor con 5 usuarios concurrentes > 5 s | Criterio (c) parcial; no afecta sesiones con un participante a la vez | Decidir entre un caché por proceso indexado por los hashes verificados y una historia precalculada offline |
| 6 pruebas PostGIS que requieren el runner con Docker | Cubiertas en parte por `postgres_migration_check.py` | Correrlas cuando se autorice Docker o un servidor descartable |
| Criterios (a), (b) y (d) del anteproyecto | Matriz incompleta | Transcribir el texto literal del anteproyecto |
| Rendimiento en producción (bundle estático) | No medido | Repetir el script contra `vite preview` |
| Retención: tarea programada de producción | Sólo el comando existe | Programarla en el despliegue institucional |
| Autorización institucional para el mapa con datos reales | La vista queda desactivada | Formalizar con el Ministerio |
