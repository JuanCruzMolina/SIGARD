# Verificación final antes de las pruebas de aceptación (P6)

Fecha: 16/11/2026 · Rama `entrenamiento-ML` · Etiquetas `v0.9.0-aceptacion` (P6) y
`v0.9.1-aceptacion` (P6.1: historia anual precalculada, rendimiento en producción, criterios
literales y límites documentados).

Estados usados: **Cumple** (implementado y verificado con la prueba citada) · **Parcial** (cumple con
límites declarados) · **Distinto** (se resolvió de otra forma que lo prometido, con justificación) ·
**Pendiente** (no cubierto).

> La matriz de módulos parte de `PRODUCT.md`, `docs/plan-proyecto.md`, el punto 13 del tutor y las
> consignas de esta etapa. Los criterios de aceptación de §2 se transcriben literalmente del
> anteproyecto (texto provisto por el responsable el 16/11/2026).

## 1. Módulos del anteproyecto

| Módulo | Especificación | Implementación | Prueba | Evidencia | Estado |
|---|---|---|---|---|---|
| 1. Ingesta y procesamiento | Carga, limpieza y procesamiento de registros epidemiológicos | Importador SISA por hash (`ml/src/sigard_ml/ingestion/epidemiology/`), consolidación etapa 1 (`forecasting/consolidation.py`), importador público y lote ficticio editable en la demo | `ml/tests/test_epidemiology_database.py`, `test_consolidation.py`, `backend/tests/test_publication_import.py` | Regresión backend e importador; consolidación documentada en `docs/database/consolidation-stage1.md` | **Parcial**: completo para el uso local y experimental; sin flujo institucional de carga en línea |
| 2. Modelo predictivo | Predicción por radio censal y semana | Visor histórico h=1 con referencia estadística y candidatos ML no promovidos (`predictive_service.py`, `HistoricalBacktest.jsx`) | `test_predictive_service.py`, `test_predictive_ml.py`, `npm run test:backtest`, `test:predictive:browser` | §6 (suite) | **Parcial**: reconstrucción retrospectiva; ningún modelo ML promovido; 2025–2026 bloqueados |
| 3. Geolocalización y visualización | Mapa ciudadano agregado («mapa de calor») | Mapa público de contexto y simulación; vista **«Actividad registrada»** con niveles por radio, supresión primaria y complementaria, desactivada sin autorización (`public_activity.py`, `PublicActivity.jsx`) | `test_public_activity.py`, `test_public_activity_package.py`, `npm run test:public-activity`, `test:public-activity:browser` | `docs/actividad-registrada-publica.md`; paquete real con 0 revelaciones (P4.1) | **Distinto**: niveles por radio con supresión en lugar de mapa de calor kernel (ver §5) |
| 4. Alertas | Alertas configurables | Reglas, evaluación semanal manual, candidatas con aprobación humana y auditoría; sin publicación ciudadana (`internal_alerts.py`) | `test_internal_alerts.py`, `npm run test:alerts`, `test:alerts:browser`; migración 06 y restricción en PostGIS (§2) | `docs/alertas-internas.md` | **Parcial**: avisos internos retrospectivos; sin correo/SMS ni alerta oficial |
| 5. Gestión de usuarios por roles | Acceso detallado sólo autenticado y autorizado | Rol `admin` con JWT HS256 versionado, alta/rotación/desactivación con confirmación, último administrador protegido | `test_admin_accounts.py`, `test_route_authorization.py`, `test:accounts:browser` (normal e integral) | §4 | **Cumple** (con la diferencia de §5: ciudadanía anónima) |
| 6. Información sanitaria administrable | Contenido preventivo editable | Borrador, publicación con versión, despublicación y auditoría (`prevention.py`); página pública desde la API con respaldo estático | `test_prevention_content.py`, `test:prevention`, `test:prevention:browser`; migración 05 y carga inicial en PostGIS (§2) | `backend/README.md` § módulo 6 | **Cumple** |

## 2. Criterios de aceptación del anteproyecto

Texto literal:

> «Los criterios mínimos de aceptación del prototipo serán: (a) todos los módulos descritos deben
> estar operativos en un entorno de prueba; (b) el modelo predictivo debe estar entrenado, evaluado
> y documentado, demostrando mediante métricas estándar una capacidad predictiva superior a la de
> un modelo de referencia (baseline) apropiado para el problema predictivo abordado; (c) el sistema
> debe responder en menos de 5 segundos ante consultas sobre el mapa de riesgo; y (d) el prototipo
> debe superar las pruebas de aceptación con al menos dos referentes del Ministerio de Salud de
> La Rioja.»

| Criterio | Evidencia | Estado |
|---|---|---|
| (a) Módulos operativos en un entorno de prueba | Matriz de §1: los seis módulos funcionan en el entorno de prueba local (`dev`, `dev:demo`, `dev:alerts` y API ficticia), con sus pruebas automáticas y recorridos de navegador aprobados (§6). Los estados *Parcial* y *Distinto* de §1 describen alcance (uso local y retrospectivo, niveles por radio en lugar de mapa de calor), no falta de funcionamiento | **Cumple**, con las diferencias declaradas en §5 |
| (b) Modelo entrenado, evaluado y documentado, superior a un baseline | **Cantidad:** `residual_v2` obtiene MAE 0,030535 frente a 0,035357 de `count_latest` (persistencia) en desarrollo 2021–2023: 13,6 % menor, ΔMAE −0,00482 con IC95 [−0,00823; −0,00195]. Evaluación walk-forward con purga temporal, protocolo prerregistrado (commit `947f71c`) y verificación independiente (28/28 cifras coinciden). **Presencia:** `rf_v2_city_propensity` empata con la persistencia (recall@10 0,160 frente a 0,156; diferencia no significativa). El criterio adicional Q2 del protocolo (error en conteos altos y sesgo) **no se cumplió** (sesgo −0,0081), por lo que ningún candidato se promovió a uso operativo. Documentación: `docs/predictive-module-final.md` («Integración de candidatos v2») y `docs/database/ml-candidates-closure.md` | **Cumple para cantidad**; presencia sin superioridad demostrada |
| (c) Respuesta < 5 s en consultas sobre el mapa de riesgo | §3: 6 operaciones, 1 y 5 usuarios, p95 sobre 30 repeticiones, en desarrollo y en producción | **Cumple en producción** (12/12 mediciones bajo 5 s, 1 y 5 usuarios); en el servidor de desarrollo, 3 cargas en frío con 5 usuarios no cumplen (§3) |
| (d) Aceptación con al menos dos referentes del Ministerio | Kit en `docs/aceptacion/` (protocolo, escenarios, SUS, criterios, acta y planilla) | **Pendiente** de las sesiones de aceptación |

## 3. Rendimiento (criterio c)

**Script reproducible:** `frontend/scripts/performance.browser.mjs`.
- Desarrollo: `npm.cmd --prefix frontend run test:performance`.
- Producción: `npm.cmd --prefix frontend run test:performance -- --target production`.
- `--only a,b` repite operaciones y `--reps N` cambia la cantidad de repeticiones.
- Levanta sus propios entornos y registra sólo tiempos en `data/interim/official/performance-v1/`
  (privado; producción en `production/`). Desde F4 cada corrida escribe sólo en una carpeta nueva
  `<etiqueta>/` (`--label`, o fecha y hora) con `results.json` y sus bundles `build-*`; si la
  carpeta existe, no corre. Nunca vacía ni sobrescribe mediciones anteriores (F0, F2).
- `--users 1` mide sólo el nivel de un usuario (verificación del arnés).

**Entorno:**
- AMD Ryzen 5 5500 (12 hilos), 16 GB de RAM, Windows 11 (10.0.26300), Node 24.15.0, Chromium 152 headless.
- Todo en el mismo equipo, con otras aplicaciones de escritorio abiertas; APIs locales uvicorn de un solo proceso.
- **Desarrollo:** servidor de Vite (módulos sin empaquetar).
- **Producción:** `vite build` (React de producción, minificado) servido con `vite preview` en el
  mismo origen, con las mismas APIs.
  - El visor predictivo no forma parte de los bundles públicos: exige la compuerta de
    investigación local (`import.meta.env.DEV`).
  - Para medirlo se compiló un bundle de medición que abre sólo esa compuerta.
  - Los bundles de medición quedan en la carpeta privada y nunca en `dist`.
- Se bloquean los orígenes externos (teselas y fuentes web, todos https) para que la red de
  Internet no influya.
- **Sin interceptación de solicitudes:** el frontend apunta directamente a la API ficticia mediante
  `VITE_API_URL` (ver la lectura del resultado).

**Volumen:**
- 263 radios oficiales en la geometría del visor.
- 208 semanas evaluables 2021–2024 (catálogo de 366 semanas).
- Visor y alertas con la API predictiva local en modo protegido.
- Historia anual precalculada instalada (`docs/predictive-module-final.md`, «Historia anual precalculada»).
- «Actividad registrada» con la fixture ficticia (24 celdas + 1 fuera del área, 45 bloques).

**Método:**
- 30 repeticiones con 1 usuario.
- 30 rondas con 5 usuarios concurrentes, cada uno en su propio contexto de navegador (150 muestras).
- p95 por rango más cercano.
- Las cargas se miden en frío: contexto nuevo por muestra, desde la navegación hasta el contenido completo.
- El cambio de semana y la consulta de radio se miden sobre un visor ya cargado, después de que
  terminaron sus cargas de fondo.
- Una muestra que supera 30 s se registra como falla (≥ 30 000 ms); nunca se descarta.

**Resultados del 16/11/2026** (p95 en ms; entre paréntesis, el máximo):

| Operación | Condición de fin | Dev, 1 usuario | Dev, 5 usuarios | Producción, 1 usuario | Producción, 5 usuarios |
|---|---|---|---|---|---|
| Carga de «Actividad registrada» (fixture) | 25 polígonos y serie dibujados | 1 339 (1 813) | **6 266** (7 123) | 604 (667) | 1 146 (1 215) |
| Carga de prevención | 27 establecimientos y contenido de la API | 1 367 (1 374) | **6 829** (7 034) | 350 (366) | 1 415 (1 476) |
| Carga del visor | semana lista y ≥ 263 polígonos | 1 954 (1 973) | **7 558** (7 903) | 815 (822) | 2 949 (30 685; 1/150 > 30 s) |
| Cambio de semana (visor cargado) | semana nueva lista | 258 (278) | 739 (789) | 180 (186) | 569 (660) |
| Consulta de radio (visor cargado) | panel del radio | 161 (175) | 307 (328) | 81 (135) | 279 (346) |
| Panel de alertas | panel con semanas evaluables | 195 (211) | 306 (326) | 174 (205) | 267 (291) |
| **Umbral 5 s** | | cumple 6/6 | **cumple 3/6** | cumple 6/6 | **cumple 6/6** |

**Lectura del resultado:**
- **Producción cumple las 12 mediciones.** Con 5 usuarios, la carga del visor tiene p95 2,9 s
  (en P6, en modo desarrollo, fue 33,5 s).
- **Desarrollo con 5 usuarios no cumple** en las tres cargas en frío (6,3–7,6 s). Las tres incluyen
  «Actividad registrada» y prevención, que no usan la API predictiva. El cuello de botella es el
  servidor de Vite, que sirve cientos de módulos sin empaquetar a 5 navegadores en frío a la vez;
  no es la API. Las operaciones sobre un visor ya cargado cumplen también en desarrollo.
- **Historia anual precalculada.** La API ya no recalcula la serie anual: `/history` pasó de unos
  6,5 s por año a 0,08 s con un usuario, y a 0,33 s con 5 solicitudes simultáneas medidas
  directamente contra la API.
- **Arnés de medición corregido.** La interceptación de solicitudes de Chromium (Puppeteer, y
  también un patrón `Fetch` de CDP limitado a la API ficticia) hacía fallar en forma intermitente
  solicitudes concurrentes a la API predictiva con `net::ERR_FAILED`, a los ~10 ms y antes de
  llegar a la API. Eso dejaba entre el 10 % y el 80 % de las cargas del visor con 5 usuarios
  detenidas hasta el límite de 30 s.
  - Sin interceptación, 60/60 cargas terminaron en 2,4–3,3 s.
  - Parte de las 48 fallas de P6 se debían a este artefacto; la otra parte, al recálculo de la
    historia, que la API ya no hace.
- **Observación abierta.** En producción, 1 de 150 cargas con 5 usuarios terminó con «No se pudo
  conectar con la API local». La consulta inicial falló y la página ofreció «Reintentar», pero la
  muestra no se recuperó sola y se contó como falla de 30 s. No se reprodujo en desarrollo
  (0/150). Se registra sin descartarla.
- Con un usuario, el uso previsto en las sesiones de aceptación, todas las operaciones cumplen
  en ambos modos.

## 4. Medidas de seguridad prometidas

| Medida | Implementación | Prueba | Estado |
|---|---|---|---|
| Disociación de datos personales | Reportes ciudadanos anónimos; el seguimiento público expone sólo código, estado, fechas y mensaje; la ubicación exacta sólo está en el panel protegido; mapa público sólo agregado (radio completo, mínimo 5) | `test_citizen_reports.py::test_anonymous_report_and_public_status_do_not_expose_location`, `test_public_activity*.py`, `test:public-activity` (ausencia en `public`/`dist`) | **Cumple** |
| RBAC / JWT | `get_current_admin` en todas las rutas `/api/v1/admin/*` salvo el login; token con `exp`, `sub` y versión; superficie pública explícita | `test_route_authorization.py` (27 rutas administrativas protegidas; 401 sin token y con token falsificado en cada una), `test_admin_accounts.py` | **Cumple** |
| Auditoría | Auditoría de reportes (actualización, exportación y, desde P6, **consulta del detalle**), de cuentas (sin credenciales), de contenido preventivo (antes/después) y de alertas | `test_citizen_reports.py::test_admin_detail_view_is_audited_without_report_content`, `test_admin_accounts.py`, `test_prevention_content.py`, `test_internal_alerts.py` | **Cumple** (consulta de detalle corregida en P6) |
| Alta de administradores | Sólo un administrador autenticado crea cuentas, con su contraseña; sin registro público ni recuperación por correo; bootstrap sólo con base vacía | `test_admin_accounts.py`, `test:accounts:browser` | **Cumple** |
| Revocación de tokens | `token_version` en rotación y desactivación; sesión propia cerrada | `test_admin_accounts.py::test_rotation_revokes_every_old_token_and_password`, `test:accounts:browser` | **Cumple** |
| Retención | Reportes con `retention_until` (180 días por defecto) y purga diaria fuera del proceso web (`app/retention.py`) | `test_citizen_reports.py::test_retention_removes_only_expired_reports` | **Parcial**: el comando existe y está probado; la tarea programada diaria queda para el despliegue institucional (el prototipo no tiene servidor de producción propio) |
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
| 2. Pruebas PostGIS omitidas (6) | **Límite documentado, no ejecutadas**: requieren el runner descartable con Docker (puerto 5435, identidad propia) y `AGENTS.md` prohíbe iniciar Docker. La cadena de migraciones sí se verificó en PostGIS real (`postgres_migration_check.py`, 11/11). No se debilitaron sus guardas | `AGENTS.md`; punto 2 anterior |
| 4. Rendimiento (P6.1) | Producción: 12/12 mediciones bajo 5 s. Desarrollo: 9/12 (las cargas en frío con 5 usuarios superan 5 s por el servidor de Vite). Historia anual precalculada y arnés sin interceptación | §3 |
| 5. Seguridad | 27 rutas administrativas exigen rol; 401 sin token o con token falso en todas; superficie pública explícita; auditoría de consulta de detalle agregada; auditoría del repositorio sin candidatos sensibles (197 controles) | `test_route_authorization.py`, `check_repository_security.py` |
| 5. Accesibilidad | Nombres accesibles, contraste AA de todo el texto visible y alcance por teclado en administración de prevención, alertas y actividad (1440 y 390 px) | `browser-a11y.mjs` en `test:prevention:browser`, `test:alerts:browser`, `test:public-activity:browser` |
| 6. Frontend | lint y build; `test:security` 15, `test:public-map` 5, `test:public-activity` 5, `test:research` 21, `test:dev` 21, `test:backtest` 22, `test:citizen` 4, `test:prevention` 5, `test:alerts` 5, `test:demo` 13: todo aprobado | — |
| 6. Backend | 360 aprobadas, 6 omitidas (PostGIS con Docker) | `publication_isolated.py --backend-regression` |
| 6. ML | 68 aprobadas (paquete público, bundles y exportaciones; sin entrenamiento ni fuentes privadas) | `pytest` de pruebas seleccionadas |
| 6. Navegador | cuentas (normal e integral), actividad, visor, ciudadano, prevención admin, alertas y demo integral: todo aprobado | — |

Límites:
- Sin lector de pantalla real ni dispositivo móvil físico.
- Rendimiento medido en un solo equipo, con cliente y servidores en la misma máquina.
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

### Corregidos en P6.1

| Defecto | Causa | Corrección | Regresión |
|---|---|---|---|
| Carga del visor con 5 usuarios > 5 s | `/history` recalculaba la serie anual en cada pedido (≈ 6,5 s por año), serializado en el proceso local | Historia anual precalculada offline, ligada a sus entradas y verificada con el mismo mecanismo; la API sólo lee | `test_predictive_history.py` (idéntica para todos los años, modos y candidatos; alterada o desactualizada bloquea); `verify` real 14/14 |
| Medición del visor distorsionada por el arnés | La interceptación de solicitudes de Chromium hacía fallar solicitudes concurrentes a la API predictiva (`net::ERR_FAILED`) | `performance.browser.mjs` sin interceptación: `VITE_API_URL` a la API ficticia y bloqueo de orígenes https | Corridas de 30 repeticiones en desarrollo y producción |

### Pendientes

| Pendiente | Impacto | Propuesta |
|---|---|---|
| Cargas en frío con 5 usuarios en el servidor de desarrollo (6,3–7,6 s) | No afecta producción ni sesiones con un participante a la vez | Usar el bundle de producción si se prueban varias sesiones simultáneas |
| 1 de 150 cargas del visor en producción terminó con «No se pudo conectar» | Mitigado en P6.2: las lecturas iniciales (visor, actividad, prevención) se reintentan una vez a los 500 ms ante falla de red o 5xx (`readRetry.mjs`); escrituras y 4xx nunca | Observar en las sesiones de aceptación; no se volvió a medir el rendimiento |
| Historia por radio (panel del radio) calculada por pedido (≈ 1,2 s por radio y año) | Fuera de las 6 operaciones medidas; puede tardar más con varias sesiones | Precalcular sólo si las sesiones lo requieren (≈ 3 700 archivos) |
| 6 pruebas PostGIS que requieren el runner con Docker | Límite documentado: `AGENTS.md` prohíbe iniciar Docker; la cadena de migraciones se verificó en PostGIS real (11/11) | Correrlas cuando se autorice Docker o un servidor descartable |
| Criterio (d): pruebas de aceptación con dos referentes del Ministerio | Aceptación pendiente | Realizar las sesiones con el kit de `docs/aceptacion/` |
| Retención: tarea programada de producción | El comando existe y está probado | Programarla en el despliegue institucional |
| Autorización institucional para el mapa con datos reales | La vista queda desactivada | Formalizar con el Ministerio |
