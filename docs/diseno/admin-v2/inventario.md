# Inventario previo a Administración v2 (F0)

Línea base del frontend antes de integrar el módulo predictivo en Administración.
Relevado el 21/11/2026 sobre `entrenamiento-ML` (`frontend/src/App.jsx:47-56`).
Etiqueta de referencia: `pre-admin-v2`.

## Modos de ejecución y APIs

| Modo | Comando | Frontend | API | Prefijos |
|---|---|---|---|---|
| Público / producción | `vite build` (Vercel) | estático | `VITE_API_URL` (por defecto `http://localhost:8000`) | `/api/v1/public/*`, `/api/v1/citizen-reports*`, `/api/v1/geocoding/address`, `/api/v1/admin/*` |
| Desarrollo local (desde F2) | `npm.cmd --prefix frontend run dev` | 127.0.0.1:5173 | Sólo la API administrativa completa 127.0.0.1:8767 (`alerts_local.py serve`, SQLite privado persistente en `data/interim/official/internal-alerts-v1/`); 8765 ya no existe | 8767 (`VITE_API_URL`): `/api/v1/admin/*` (sesión, reportes, contenido, cuentas, alertas), `/api/v1/public/*`, `/api/v1/citizen-reports*` y `/api/v1/research/predictive/*` (visor: guard local + JWT de administrador; consultas privadas auditadas) |
| Demo integral | `run dev:demo` | 127.0.0.1:5173 | API demo 127.0.0.1:8766 (SQLite temporal) | `/api/v1/admin/*`, `/api/v1/admin/demo/*`, `/api/v1/citizen-reports*` |
| Alias obsoleto | `run dev:alerts` | igual que `dev` | igual que `dev` | igual que `dev` |

**F1 (`feature/admin-f1-dev-unificado`).** `dev` reemplaza al antiguo `dev:alerts`: el
coordinador es `frontend/scripts/dev.mjs` con el runtime de `frontend/scripts/dev-alerts.mjs`.
Sin cuenta local, `dev` arranca igual, el login responde «Credenciales inválidas» y la terminal
muestra `alerts_local.py create-admin`. En 8767, `/api/v1/public/weeks` responde 503 (el sitio
usa los JSON estáticos), `/api/v1/public/activity` responde 404 salvo con
`SIGARD_PUBLIC_ACTIVITY=fixture`, y `/api/v1/public/prevention` sirve lo publicado desde el panel.
`/api/v1/geocoding/*` responde 503 en local. Como antes de F1, `dev` carga IBM Plex Sans desde Google Fonts
(`fonts.googleapis.com` y `fonts.gstatic.com`); sólo `dev:demo` quita esa hoja para funcionar sin conexión. Antes de F1, `dev` no tenía API administrativa y el
frontend apuntaba a `localhost:8000`.

`localResearchEnabled()` (`services/experimentalResults.js`) cambia `/` → `/mapa` y
`/mapa` del mapa público al visor predictivo. Los datos de prevención salen de
`/data/prevention_content.json` y `/data/health_facilities.geojson` (estáticos), con
contenido publicado en `/api/v1/public/prevention`.

## Rutas

| Ruta | Página → componentes principales | Datos / API | Pruebas que la cubren |
|---|---|---|---|
| `/` | `Dashboard` (`SigardComponents`: StatCard, TerritorialMap, TopRadios). Desde F3 (pendiente) también en dev es la portada pública, sin redirección | `services/sigardData.js` → `/data/*.json` o `:8000/api/v1/public/{weeks,territorial-context,model-evaluation,metadata,predictions,experimental-spatial-history}` | `test:security`, `test:public-map`, `test:accounts:browser` (`/dashboard`) |
| `/dashboard` (sólo dev) | `Dashboard` | igual que `/` | `test:accounts:browser`, `test:research` (`local-entry`) |
| `/mapa` (siempre público, F3) | `Mapa` (`TemporalControls`, `TerritorialMap`); en dev, enlace «El módulo predictivo está en Administración» y, con sesión de administrador, `/mapa?<estado del visor>` redirige a `/admin/predictivo?…` | `sigardData.js` (`:8000/api/v1/public/*`) | `test:public-map`, `test:research` (`local-entry`), `test:demo:browser`, `test:predictive:browser` |
| `/admin/predictivo` (F3) | `AdminPredictivo` (`AdminLoginForm` sin sesión) → `HistoricalBacktest` (`WeekTimeline`, `SummaryCards`, `BacktestMaps`, `BacktestHistory`, `RadioPanel`, `ModelPerformance`, `MLComparison`, `DataTable`) | `services/backtestResults.js` + `adminSession.mjs` → `127.0.0.1:8767/api/v1/research/predictive/*` con el token de la sesión de Administración (F2/F3) | `test:backtest` (backtest, predictive-view, private-view), `test:predictive:browser` (ficticia y `--real`, entorno propio en modo sesión), `test:dev`; backend `test_predictive_access.py` |
| `/validacion` | `Validacion` (`BacktestChart`) | `sigardData.js` | `test:research` (`local-entry`) |
| `/metodologia` | `Metodologia` | `sigardData.js` | `test:research` (`local-entry`) |
| `/prevencion` (y `*`) | `Prevencion` → `PreventionGuide`, `SymptomsAlert`, `HealthFacilitiesMap`, `RestrictedMarkdown`, `CitizenReportForm`, `ReportConfirmation`, `ReportStatusLookup` | `services/preventionData.js` (`/data/*`), `citizenReports.js` → `/api/v1/public/prevention`, `/api/v1/citizen-reports`, `/citizen-reports/status/{código}`, `/geocoding/address` (`:8000`, o `:8766` en demo) | `test:prevention`, `test:citizen`, `test:citizen:browser`, `test:prevention:browser`, `test:demo:browser` |
| `/actividad` | `Actividad` → `PublicActivity` (el enlace aparece sólo si la API sirve un paquete habilitado) | `services/publicActivity.mjs` → `:8000/api/v1/public/activity` | `test:public-activity`, `test:public-activity:browser` |
| `/admin/reportes` | `AdminReports` (`AdminLoginForm`, bandeja, detalle, exportar CSV, desde F4 dentro de `AdminLayout`) | `citizenReports.js` → `/api/v1/admin/session`, `/admin/citizen-reports*`, `/admin/citizen-reports/export.csv` | `test:citizen`, `test:citizen:browser`, `test:accounts:browser`; backend `test_citizen_reports.py`, `test_route_authorization.py` |
| `/admin/cuentas` (F4; antes panel `accounts`) | `AdminAccounts` | `/api/v1/admin/users*` (alta, desactivar, contraseña) | `test:accounts:browser`; backend `test_admin_accounts.py` |
| `/admin/contenido` (F4; antes panel `prevention`) | `AdminPrevention` | `/api/v1/admin/prevention*` (borrador, publicar, historial) | `test:prevention`, `test:prevention:browser`; backend `test_prevention_content.py` |
| `/admin/alertas` (F4; antes panel `alerts`, no demo) | `AdminAlerts` | `/api/v1/admin/alerts*`, `/admin/alerts/candidates/export.csv` (`VITE_API_URL`: `:8000` en producción, `:8767` con `dev`) | `test:alerts`, `test:alerts:browser`; backend `test_internal_alerts.py` |
| ↳ panel `demo` (sólo demo) | `DemoWorkspace` | `:8766/api/v1/admin/demo/*` | `test:demo`, `test:demo:browser` |

Las suites transversales son `test:dev` (orquestación de `dev` y proxy de navegador),
`test:read-retry` (reintentos de lectura) y `test:research` (resultados y análisis
experimentales, entrada local).

## Notas para Administración v2

- Hasta F3 los paneles de Administración eran estados internos (`panel`) de `/admin/reportes`
  y la única subruta propia era `/admin/predictivo`. Desde F4 cada sección tiene ruta propia (ver
  abajo); sólo el espacio de la demo sigue como panel interno de `/admin/reportes`. Las maquetas (`Main`, `Predictivo`,
  `Alertas`, `Reportes`, `Contenido`, `Cuentas`, `Ingreso`) suponen navegación propia.
- Desde F3 el visor predictivo está en `/admin/predictivo` y desde F2 consume la API
  administrativa local (8767, cabecera `X-Sigard-Research` + `Authorization` con el token de
  la sesión de Administración). `app.main` (producción) y la demo (8766) no contienen sus rutas.
- `test:accounts:browser` y `test:public-activity:browser` requieren `dev` en marcha y
  redirigen 8000 y 8767 a su propia API ficticia (`ADMIN_API_PORTS` en
  `frontend/scripts/browser-proxy.mjs`). Las demás pruebas de navegador exigen
  5173/8766/8767 libres y levantan sus propias fixtures; `test:alerts:browser` y, desde F2,
  `test:predictive:browser` usan el mismo runtime que `dev`, en modo sesión con SQLite y
  cuenta descartables.
- Las rutas en `:8000` de la tabla corresponden al `VITE_API_URL` por defecto (producción);
  con `dev` las mismas rutas van a `:8767`.

## F4 · Marco de Administración v2

Implementado en `entrenamiento-ML` (23/11/2026), sin rediseñar el contenido de las pantallas.

- **Rutas** (`pages/AdminArea.jsx`, montado en `/admin/*`): `/admin` → `/admin/inicio`;
  `inicio` y `auditoria` muestran «Próximamente»; `predictivo` (`AdminPredictivo`), `alertas`,
  `reportes`, `contenido` y `cuentas` (`AdminReports` con `section`). Las rutas desconocidas bajo
  `/admin/` van a Inicio. El enlace público «Administración» apunta a `/admin`.
- **Marco** (`components/AdminLayout.jsx` + `.css`, `services/adminShell.mjs`): menú lateral
  `#123a3d` con grupos Operación/Gestión, ítem activo `#dceee7` con `aria-current`, contadores
  `#a64a12`; caja de contexto (entorno, divulgación «Protegida» y «Datos hasta»); barra superior
  con acceso restringido, minutos de sesión (claim `exp`), correo usado al ingresar y «Cerrar sesión». Bajo 900 px el menú
  se apila arriba y se despliega con «Menú». Dentro del marco se ocultan la franja, el encabezado y
  el pie públicos; el formulario de ingreso sigue fuera del marco.
- **Contadores**: alertas = `pending` de `GET /api/v1/admin/alerts/status`; reportes = `total` de
  `GET /api/v1/admin/citizen-reports?status=recibido&page_size=1`. Sin número si la API falla o
  devuelve 0. En la demo no hay ítem de alertas internas; el visor sólo aparece con
  `localResearchEnabled()`.
- **«Datos hasta»**: en investigación local con sesión de administrador es la última semana
  evaluable del visor (`availability_status = available`), leída del mismo `/calendar` y la misma
  caché que el visor, con la SE y el año de la API (SE 52/2024 con la fixture y con `--real`). Sin
  visor (producción, demo) se muestra la semana del manifiesto público `/data/available_weeks.json`
  y el texto emergente indica la fuente.
- **Sesión**: la API administrativa no tiene un endpoint que devuelva el usuario de la sesión (sólo
  el listado paginado de cuentas con `current_user_id`), así que la barra muestra el correo escrito
  al ingresar: el formulario guarda `sigard_admin_email` en `sessionStorage` y `adminSession.mjs`
  sigue sin escribir. Al cerrar sesión, al vencer (temporizador del marco en `exp`), ante un 401 o
  con un token vencido al llegar se borran token y correo.
- **Encabezados**: se quitaron los botones de navegación («Módulo predictivo», «Alertas internas»,
  «Contenido preventivo», «Gestionar cuentas», «Volver a reportes») y el «Cerrar sesión» duplicado;
  se conservan «Exportar CSV» y «Análisis y alertas demo» (con su «Volver a reportes»).
- **Tipografía**: IBM Plex Mono (500/600) por la misma hoja de Google Fonts que IBM Plex Sans;
  token `--font-mono` en `App.css` para semanas, códigos y cifras del marco.
- **Pruebas**: `test:admin` (unitarias y contratos) y `test:admin:browser` (navegación, ítem
  activo, teclado, 390 px, barra, contexto, contadores; capturas privadas en
  `data/interim/official/ux-admin-v2-f4/<etiqueta>/`; `--real` sólo compara «Datos hasta» con el
  servicio real). Las pruebas de navegador previas abren las secciones desde el menú lateral.
- **Salidas privadas de los arneses** (`scripts/private-output.mjs`): performance, predictive,
  alerts, public-activity, backtest y admin-shell escriben sólo en una carpeta nueva por etiqueta
  (`--label`/`SIGARD_SHOTS_LABEL`, o fecha y hora) y no corren si existe; ninguno vacía, borra ni
  sobrescribe nada en `data/`. Contrato en `scripts/private-output.test.mjs` (`test:dev`).

## F5 · Inicio

Implementado en `entrenamiento-ML` (23/11/2026) según `Main.dc.html`, sin copiar su marcado.

- **Ajustes de F4** (antes de F5): bajo 900 px la barra superior ocupa una línea (candado,
  vencimiento y correo truncado) y «Cerrar sesión» pasa al final del menú desplegable; subtítulo
  único para todas las pantallas (17 px, 15 px en móvil). Los filtros de `/admin/reportes` en
  móvil ya estaban sin margen interior antes de F4 (captura `ux-admin-v2-f4/antes`): queda para F6.
- **Pantalla** (`pages/AdminInicio.jsx`, `components/AdminInicio.css`, helpers puros en
  `services/adminHome.mjs`). Sin endpoints nuevos ni cambios de contrato; fuentes:
  - alertas: `GET /api/v1/admin/alerts/candidates?status=pending` (cantidad = largo de la lista;
    no se consulta en la demo);
  - reportes: `GET /api/v1/admin/citizen-reports?status=recibido&page_size=10` (`total`); para
    los más antiguos se leen la última página y, si es corta, la anterior (la API ordena por
    `created_at` descendente);
  - contenido: `GET /api/v1/admin/prevention`, secciones con `has_pending_changes`;
  - semana: `services/adminWeek.js`, la misma función que «Datos hasta» del menú;
  - modelos e integridad: `/calendar` del visor (misma caché); 503 = paquete no verificado;
  - mapa público: `loadActivity()`; 404 = desactivado. Desde F5 una falla de red, otro estado o
    un paquete inválido devuelven además `unavailable: true` («No disponible» en Inicio; las
    páginas públicas siguen tratándolo como desactivado).
  Una fuente que no responde muestra «No disponible»; un 401/403 cierra la sesión.
- **Destino tras el ingreso**: cada pantalla conserva su URL al ingresar; `/admin` y las rutas
  desconocidas van a `/admin/inicio`. Los mensajes de `dev` y `dev:demo` apuntan a `/admin`.
- **Pruebas**: `test:admin` (helpers y contratos de Inicio) y `test:admin:home:browser` (destino
  tras el ingreso; API real descartable; fixtures generadas con datos, vacía y con una API
  fallando; mapa activado/desactivado/no disponible; AA, teclado, 390 px). Capturas privadas en
  `data/interim/official/ux-admin-v2-f5/<etiqueta>/`; la captura previa de Inicio es
  `ux-admin-v2-f4/f5-ajustes-f4/inicio-*` (después de los ajustes F4, antes de F5).

## F6.1 · Contención visor/alertas, ajustes de Inicio y Módulo predictivo

Implementado en `entrenamiento-ML` (24/11/2026). Etiqueta previa: `antes-f6-1`.

- **Contención 8767** (reproducción determinista: `performance.browser.mjs --target production
  --only visor_carga,visor_cambio_semana,visor_consulta_radio,panel_alertas`; diagnóstico con
  `--trace-slow`). Antes: panel de alertas con 1 usuario p95 5.308 ms, máx. 20.044 ms. Tres
  causas encadenadas:
  1. `backtest_api`: sin `response_model`, FastAPI codificaba el JSON del visor en el bucle de
     eventos; ahora se codifica en el hilo del endpoint con los mismos bytes (`encoded`).
  2. `PredictiveGate`: las consultas del visor cuyo cliente ya se desconectó no se calculan
     (499); antes se procesaban en cola tras cerrar pestañas o contextos.
  3. Frontend: respuestas cuyo cuerpo no se leía (404 de la sonda de actividad, 5xx
     reintentados, errores del visor) mantenían abiertas conexiones HTTP/1.1 hasta su tiempo
     límite; `readRetry.discardBody()` las libera.
  Después: panel con 1 usuario p95 124–182 ms, máx. 145–588 ms. Pruebas:
  `test_predictive_access.py` (bytes idénticos, bucle libre durante una codificación grande
  —falla sin el arreglo—, consulta abandonada no calculada) y `test:read-retry`.
- **Inicio**: en móvil 5 pendientes y «Ver más» (10), fila completa como área táctil; textos
  ≥ 14 px; «SE 52/2024» sin espacio doble (monoespaciada con `word-spacing`); tarjetas
  superiores de igual altura; el doble borde de «Revisar alertas» es sólo el foco de teclado.
- **Componentes comunes** (`components/AdminUI.jsx` + `.css`): `ScreenHeader` (ruta, título,
  subtítulo, aside), `Card`, `Badge`, `Notice`, `UiButton` (botón o enlace, 44 px) y `UiTable`.
- **Módulo predictivo** (`/admin/predictivo`, `Predictivo.dc.html`), sólo presentación: mismos
  controles, textos, contratos y privacidad. Columna lateral «Radios priorizados esta semana» /
  «Radios con más registros esperados» (`predictiveView.priorityList`): sólo radios que el mapa
  ya muestra (misma `cellCategory`); en modo protegido nunca se listan radios protegidos, a
  diferencia de la maqueta (que muestra «Protegido»), para no revelar predicciones que el mapa
  oculta. Diferencias deliberadas con la maqueta: se conserva el título y los textos actuales;
  «¿Qué tan bien funciona el modelo?» sigue plegable (las pruebas y la lectura actual lo usan
  así); no hay «Ver los 10 con su historial» (no existe esa vista; el historial está en el
  panel del radio).
- **Pruebas**: `test:predictive:layout:browser` (nuevo: carga, protegido/privado,
  ¿Dónde?/¿Cuántos?, lista = API, panel por teclado, semana vacía, error, 1440/390, AA, 44 px,
  ≥ 14 px); capturas en `data/interim/official/ux-admin-v2-f6/<etiqueta>/`; capturas del visor
  completo antes/después en `ux-predictive-redesign-20261112/<etiqueta>/`.- **Rendimiento** (`performance.browser.mjs --target production`, 1 y 5 usuarios, p95 en ms;
  F0 `results.json`, F2 `results-f2-final.json`, F5 `f5-rendimiento`, F6.1 `f6-1-rendimiento`):

  | Operación | Usuarios | F0 | F2 | F5 | F6.1 |
  |---|---|---|---|---|---|
  | actividad (fixture) | 1 / 5 | 604 / 1.146 | 344 / 1.297 | 314 / 1.313 | 390 / 1.281 |
  | prevención | 1 / 5 | 350 / 1.415 | 426 / 1.359 | 326 / 1.312 | 403 / 1.312 |
  | visor: carga | 1 / 5 | 815 / 2.949 | 1.083 / 3.828 | 1.079 / 4.069 | 1.075 / 3.675 |
  | visor: cambio de semana | 1 / 5 | 180 / 569 | 190 / 826 | 190 / 685 | 171 / 741 |
  | visor: consulta de radio | 1 / 5 | 81 / 279 | 100 / 350 | 89 / 260 | 82 / 261 |
  | panel de alertas | 1 / 5 | 174 / 267 | 141 / 428 | 3.677 / 385 | 1.750 / 505 |

  Presupuesto de la carga del visor con 5 usuarios (≤ 4.069 ms): cumplido (3.675). Panel de
  alertas con 1 usuario: máximo 20.037 → 1.852 ms; en la secuencia aislada visor→panel, p95
  124–182 ms. El residuo de la corrida completa (2 de 30 muestras > 1,7 s) no se investigó más.

## F6.2 · Alertas internas

Implementado en `entrenamiento-ML` (24/11/2026). Etiqueta previa: `antes-f6-2`.

- **Pantalla** (`components/AdminAlerts.jsx` + `.css`, `Alertas.dc.html`), sólo presentación con
  `AdminUI`: encabezado con ruta y «Nueva regla» (abre el formulario en Reglas); franja
  «Ningún algoritmo publica alertas» con los 5 pasos de `FLOW_STEPS` y los textos de canal y
  reconstrucción; pestañas subrayadas (mismos `data-tab`/`aria-pressed`); candidatas en
  tarjetas con insignia de estado (ícono + texto), ficha (regla, condición, pregunta y modelo,
  SE calculada con `epiWeekOf`), evidencia en `UiTable` y «Ver en el mapa» (visor en la semana y
  la pregunta de la regla; sólo con `localResearchEnabled()`; el radio se pasa sólo si es un
  código censal de 9 dígitos); columna lateral con «Evaluar una semana» y «Reglas activas»;
  reglas, formulario e historial en tarjetas; errores y resultados con `Notice`. Mismas
  peticiones, validaciones, flujo de aprobar/descartar, auditoría y textos.
- **Diferencias deliberadas con la maqueta**:
  - Las candidatas pendientes se muestran todas desplegadas (la maqueta pliega las siguientes
    tras un botón «Revisar»): plegarlas cambiaría el flujo de revisión.
  - La decisión mantiene el flujo actual (elegir aprobar o descartar y luego escribir el
    comentario o el motivo); la maqueta muestra el comentario siempre visible.
  - «Reglas activas» no muestra «Se habría activado N veces»: ese dato sólo existe al calcular
    la vista previa de una regla y no se guarda; no se inventa ni se recalcula al abrir.
  - En lugar de «Evaluar la próxima semana pendiente» se conserva el selector de semana con
    «Evaluar semana» (la API no informa cuál es la próxima semana pendiente).
  - La ficha no repite «Registros observados»: el observado ya figura en la evidencia, con la
    misma protección (< 5 → «protegido»); no se muestra nada que el modo protegido oculte.
  - Se conserva la pestaña «Cómo funciona» y el subtítulo actual.
- **Pruebas**: `test:alerts` y `test:alerts:browser` pasan sin cambios. Nuevo
  `test:alerts:layout:browser` (sin candidatas, con candidatas, aprobada, descartada, formulario,
  error de API, 1440/390, AA, teclado, 44 px, textos ≥ 14 px). Capturas en
  `data/interim/official/ux-admin-v2-f6-2/<etiqueta>/`; antes/después del recorrido completo en
  `ux-internal-alerts-20261114/f6-2-antes/` y `.../f6-2-regresion/`.
- **Rendimiento** (`performance.browser.mjs --target production`, completo, p95 en ms, 1 / 5
  usuarios; F6.2 `f6-2-rendimiento`):

  | Operación | F0 | F2 | F5 | F6.1 | F6.2 |
  |---|---|---|---|---|---|
  | actividad (fixture) | 604 / 1.146 | 344 / 1.297 | 314 / 1.313 | 390 / 1.281 | 353 / 931 |
  | prevención | 350 / 1.415 | 426 / 1.359 | 326 / 1.312 | 403 / 1.312 | 335 / 1.202 |
  | visor: carga | 815 / 2.949 | 1.083 / 3.828 | 1.079 / 4.069 | 1.075 / 3.675 | 917 / 2.905 |
  | visor: cambio de semana | 180 / 569 | 190 / 826 | 190 / 685 | 171 / 741 | 148 / 514 |
  | visor: consulta de radio | 81 / 279 | 100 / 350 | 89 / 260 | 82 / 261 | 69 / 221 |
  | panel de alertas | 174 / 267 | 141 / 428 | 3.677 / 385 | 1.750 / 505 | 143 / 293 |

  Panel de alertas: máximo 144 ms con 1 usuario y 844 ms con 5 (F6.1: 1.852 y 670).
- **Observado, sin cambiar**: el contador del menú lateral se actualiza al cambiar de sección, no
  tras decidir una candidata en la misma pantalla (comportamiento previo de F4).
