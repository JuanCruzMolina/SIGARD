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
`/api/v1/geocoding/*` responde 503 en local. Desde F7a IBM Plex Sans e IBM Plex Mono se sirven desde el
propio proyecto (`src/fonts.css`, `src/assets/fonts/`) en todos los modos; hasta F7a `dev` las pedía a
Google Fonts y `dev:demo` quitaba esa hoja para funcionar sin conexión. Antes de F1, `dev` no tenía API administrativa y el
frontend apuntaba a `localhost:8000`.

`localResearchEnabled()` (`services/localResearch.js`; hasta F7b en `services/experimentalResults.js`) cambia `/` → `/mapa` y
`/mapa` del mapa público al visor predictivo. Los datos de prevención salen de
`/data/prevention_content.json` y `/data/health_facilities.geojson` (estáticos), con
contenido publicado en `/api/v1/public/prevention`.

## Rutas

| Ruta | Página → componentes principales | Datos / API | Pruebas que la cubren |
|---|---|---|---|
| `/` | `Dashboard` (`SigardComponents`: StatCard, TerritorialMap, TopRadios). Desde F3 también en dev es la portada pública, sin redirección (`local-entry.test.mjs` lo comprueba en todos los contextos) | `services/sigardData.js` → `/data/*.json` o `:8000/api/v1/public/{weeks,territorial-context,metadata,predictions,experimental-spatial-history}` | `test:security`, `test:public-map`, `test:accounts:browser` (`/dashboard`) |
| `/dashboard` (sólo dev) | `Dashboard` | igual que `/` | `test:accounts:browser`, `test:research` (`local-entry`) |
| `/mapa` (siempre público, F3) | `Mapa` (`TemporalControls`, `TerritorialMap`); en dev, enlace «El módulo predictivo está en Administración» y, con sesión de administrador, `/mapa?<estado del visor>` redirige a `/admin/predictivo?…` | `sigardData.js` (`:8000/api/v1/public/*`) | `test:public-map`, `test:research` (`local-entry`), `test:demo:browser`, `test:predictive:browser` |
| `/admin/predictivo` (F3) | `AdminPredictivo` (`AdminLoginForm` sin sesión) → `HistoricalBacktest` (`WeekTimeline`, `SummaryCards`, `BacktestMaps`, `BacktestHistory`, `RadioPanel`, `ModelPerformance`, `MLComparison`, `DataTable`) | `services/backtestResults.js` + `adminSession.mjs` → `127.0.0.1:8767/api/v1/research/predictive/*` con el token de la sesión de Administración (F2/F3) | `test:backtest` (backtest, predictive-view, private-view), `test:predictive:browser` (ficticia y `--real`, entorno propio en modo sesión), `test:dev`; backend `test_predictive_access.py` |
| `/validacion`, `/metodologia` (retiradas) | Redirección a `/` (`Navigate`); se quitaron `Validacion`, `Metodologia` y `BacktestChart`. `sigardData.js` ya no pide `model-evaluation` y el endpoint se retiró (404); `model_evaluation.json` sigue en el paquete de publicación | — | `test:research` (`local-entry`), `test:accounts:browser` (modo integral) |
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
- **Tipografía**: IBM Plex Mono (500/600) por la misma hoja de Google Fonts que IBM Plex Sans (locales desde F7a);
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
- **Observado en F6.2** (resuelto en F6.3): el contador del menú lateral se actualizaba al cambiar
  de sección, no tras decidir una candidata en la misma pantalla.

## F6.3 · Pendientes del visor y del menú; Reportes ciudadanos

Implementado en `entrenamiento-ML` (24/11/2026). Etiqueta previa: `antes-f6-3`.

- **Pendientes**:
  - Visor en 390 px: el selector de modelo usa nombres cortos (`METHOD_SHORT_NAMES`: «Bosque
    aleatorio v2», …; la descripción debajo conserva el nombre completo y «Experimental, no
    aprobado para uso operativo»); selector, descripción y «Datos usados / Semana previa» van
    dentro de «Opciones avanzadas» (plegado); la (i) del clima queda junto a «… mm». Escritorio
    sin cambios. `services/useMediaQuery.js` (≤ 700 px).
  - Contador del menú lateral: se vuelve a consultar (mismos endpoints `/alerts/status` y
    `citizen-reports?status=recibido&page_size=1`) en cuanto se decide o evalúa una alerta
    (`AdminCountersContext`) o se guarda un reporte (`countersVersion` de `AdminLayout`).
- **Pantalla Reportes** (`pages/AdminReports.jsx` + `AdminReports.css`, `Reportes.dc.html`), sólo
  presentación con `AdminUI` (nuevo tono `info` en `Badge`): encabezado con ruta y «Exportar CSV»;
  aviso «Información privada» como `Notice` dorado; filtros en tarjeta con margen interior;
  listado en `UiTable` (Código en IBM Plex Mono, Tipo, Recibido, Estado con insignia e ícono) con
  la fila entera como objetivo; «Anterior»/«Siguiente» de 44 px y contraste AA; detalle en tarjeta
  lateral (≥ 1200 px) con ficha (Tipo, Barrio), descripción, ubicación exacta y mapa, formulario y
  «Retención hasta». En pantallas apiladas (< 1200 px) el panel vacío «Seleccioná un reporte» no
  se muestra y, al elegir un reporte, el detalle aparece debajo y se desplaza a la vista. En 390 px
  las filas son tarjetas de dos líneas (la tabla conserva su semántica). Mismos estados,
  transiciones, peticiones, CSV, auditoría, validaciones y textos.
- **Diferencias deliberadas con la maqueta**:
  - Filtros: se conservan los reales (Categoría, Estado, Barrio, Desde, Hasta, «Limpiar
    filtros»), que se aplican al cambiar; la maqueta muestra «Código de seguimiento» y «Aplicar»,
    que la API de listado no ofrece.
  - Estados: se conservan los seis reales («Recibido», no «Nuevo»; también «Pendiente de
    derivación» y «Derivado»).
  - Detalle: no hay «Contacto» (los reportes son anónimos; el dato no existe). Se rotula
    «Ubicación exacta» (la maqueta dice «aproximada», pero el detalle muestra la coordenada
    exacta). No se agregan textos nuevos de la maqueta («su consulta queda auditada», que ya
    cumple la API y explica el manual; «Los reportes vencidos se eliminan automáticamente»): se
    conserva la fecha «Retención hasta» del reporte. Se mantienen «Mensaje
    público» e «ID de posible duplicado» y el rótulo «Estado».
  - Lista: no muestra barrio, descripción ni coordenadas (sólo código, tipo, fecha y estado);
    la descripción y la ubicación exacta se cargan sólo en el detalle protegido.
  - Se conserva el subtítulo actual («Operación interna. Estos registros no son casos de dengue
    ni evidencia epidemiológica.»).
- **Pruebas**: `test:citizen:browser`, `test:demo:browser` y `test:accounts:browser` pasan
  actualizando sólo selectores (fila de la tabla, `h2 .report-code`, `.report-status`). Nuevo
  `test:reports:layout:browser` (API SQLite descartable; sin reportes, con reportes en dos
  páginas, filtros, detalle, cambio de estado con el contador 27 → 26 sin cambiar de sección,
  CSV filtrado, error de API; 1440/390, AA, teclado, 44 px, textos ≥ 14 px, listado sin recortes y
  sin datos privados; `--before` sólo captura). `test:predictive:layout:browser` comprueba el
  visor en móvil y `test:alerts:layout:browser` el contador al decidir. Capturas en
  `data/interim/official/ux-admin-v2-f6-3/<etiqueta>/` (Reportes) y
  `ux-admin-v2-f6/<etiqueta>/` (visor); antes: `f6-3-antes`, después: `f6-3-regresion`.
- **Rendimiento** (`performance.browser.mjs --target production`, completo, p95 en ms, 1 / 5
  usuarios; F6.3 `f6-3-rendimiento`):

  | Operación | F0 | F2 | F5 | F6.1 | F6.2 | F6.3 |
  |---|---|---|---|---|---|---|
  | actividad (fixture) | 604 / 1.146 | 344 / 1.297 | 314 / 1.313 | 390 / 1.281 | 353 / 931 | 305 / 802 |
  | prevención | 350 / 1.415 | 426 / 1.359 | 326 / 1.312 | 403 / 1.312 | 335 / 1.202 | 307 / 1.065 |
  | visor: carga | 815 / 2.949 | 1.083 / 3.828 | 1.079 / 4.069 | 1.075 / 3.675 | 917 / 2.905 | 946 / 2.783 |
  | visor: cambio de semana | 180 / 569 | 190 / 826 | 190 / 685 | 171 / 741 | 148 / 514 | 192 / 534 |
  | visor: consulta de radio | 81 / 279 | 100 / 350 | 89 / 260 | 82 / 261 | 69 / 221 | 71 / 208 |
  | panel de alertas | 174 / 267 | 141 / 428 | 3.677 / 385 | 1.750 / 505 | 143 / 293 | 111 / 362 |

  Panel de alertas: máximo 755 ms con 1 usuario y 492 ms con 5. Las subas frente a F6.2 (visor
  con 1 usuario, cambio de semana, panel con 5 usuarios) están dentro de la variación entre
  corridas: en la misma sesión, una repetición de F6.3 (`f6-3-rendimiento-2`) dio 955 / 3.864,
  209 / 639, 88 / 291 y 144 / 394, y el código de `antes-f6-3` (`f6-3-diag-rendimiento-base`)
  1.231 / 3.454, 180 / 684, 70 / 232 y 171 / 434 (visor carga, cambio de semana, consulta de
  radio, panel de alertas). La vista Reportes no tiene operación propia en esta medición.
- **Observado en F6.3** (resuelto después, ver «Estabilidad»): `test:predictive:browser --real`
  fallaba de forma intermitente también con el código de `antes-f6-3`.

## Estabilidad · ingreso con interceptación, carrera de la prueba y ventanas en Windows

Implementado en `entrenamiento-ML` (24/11/2026), después de F6.3 y antes de F6.4.

- **Fallo del ingreso en `test:predictive:browser --real`** (`POST /api/v1/admin/session` →
  `net::ERR_FAILED` tras el preflight):
  - Causa: la interceptación de peticiones de DevTools (dominio `Fetch`, la que usa
    `setRequestInterception` de Puppeteer). Con ella activa, Chromium a veces cancela el POST con
    preflight CORS en el mismo milisegundo en que termina su preflight. No afecta a usuarios reales.
  - Evidencia del navegador: en el registro de red de Chromium el POST sale completo (cuerpo de 86
    bytes) y 5 ms después figura `CANCELLED`, sin error de conexión ni bloqueo CORS
    (`Network.loadingFailed` sin `blockedReason` ni `corsErrorStatus`).
  - Evidencia del servidor: con un registro liviano del lado del servidor, en los fallos el POST
    llegó y se respondió `200` con `access-control-allow-origin`, mientras el navegador ya lo había
    dado por fallido.
  - Con un registro del servidor que escribe en cada petición, el fallo desaparece (0 de 18
    corridas y 0 de 80 ingresos): la respuesta se demora unos milisegundos y se cierra la ventana
    de la carrera.
  - Tasas medidas con una reproducción del mismo paso, con interceptación (20 sesiones, 4 ingresos
    cada una):

    | Código | Ingresos fallidos |
    |---|---|
    | `antes-f6-1` | 4 / 77 |
    | `antes-f6-2` | 3 / 72 |
    | HEAD | 6 / 103 |
    | HEAD sin interceptación | 0 / 60 |

    La hipótesis de los cambios de contención de F6.1 no se sostiene: ningún commit del rango lo
    introduce.
  - Corrección: en `--real` la prueba ya no habilita la interceptación. Observa las peticiones con
    las mismas comprobaciones y bloquea lo externo con el resolvedor del navegador
    (`--host-resolver-rules`). La corrida ficticia sigue interceptando porque sirve el fixture.
  - Resultado: 20 de 20 corridas seguidas de `--real`; antes fallaban alrededor de la mitad, entre
    este fallo y la carrera de la línea 361.
  - `test:demo:browser` tenía el mismo problema en el `POST` de la carga de CSV ficticio (falló 4 de
    8 corridas después del cambio de `dev.mjs`; antes había pasado en todas las regresiones,
    posiblemente por un cambio de tiempos, sin verificar). Esa prueba interceptaba sólo para dejar
    pasar lo local y registrar lo externo; ahora observa sin interceptar y bloquea lo externo con el
    resolvedor. Resultado: 10 de 10, con las mismas comprobaciones (11, 0 errores, 0 peticiones
    externas inesperadas).
  - Pendiente: otras 12 suites de navegador siguen interceptando porque inyectan errores o sirven
    fixtures. Pasaron en la regresión, pero un `POST` con preflight puede toparse con la misma carrera
    de Chromium.
- **Carrera de la línea 361**:
  - La prueba contaba como de producción una carga de año en segundo plano del visor de desarrollo
    que salía al cambiar de página.
  - Ahora espera explícitamente a que el visor quede quieto antes de contar: sin peticiones en
    curso ni nuevas durante 1 s.
  - Las peticiones de un documento descartado (recarga, navegación) dejan de contar como en curso.
- **CORS en errores**:
  - Un error no controlado lo responde `ServerErrorMiddleware`, por fuera de `CORSMiddleware`.
    Ahora el 500 lleva `Access-Control-Allow-Origin` para los orígenes permitidos, con un mensaje
    genérico sin detalle interno.
  - El 503 de geocodificación de la API local también lleva el encabezado.
  - Prueba: `backend/tests/test_error_cors.py`.
- **Ventanas en Windows**:
  - `dev.mjs` lanzaba la API con `detached` + `windowsHide`. En Windows `detached` es
    `DETACHED_PROCESS`, que anula la consola oculta, y el Python real del lanzador del venv abría
    una consola visible (Windows Terminal).
  - Ahora en Windows se lanza sólo con `windowsHide`. El hijo tiene su propia consola sin ventana,
    sigue sin recibir el Ctrl+C de la terminal y el nieto la hereda.
  - Python de pruebas y herramientas: `creationflags=NO_WINDOW` (`CREATE_NO_WINDOW` sólo si el
    proceso no tiene consola).
  - `test:dev` incluye `hidden-windows.test.mjs`, que falla ante un `spawn`/`exec*`/`fork` sin
    `windowsHide`, con `shell: true` o con `detached: true`, y ante `subprocess` sin `creationflags`.
  - Verificado con un registro de ventanas visibles: antes del cambio, `dev` abría una ventana de
    Windows Terminal con la consola de Python; después, ninguna en `dev`, las suites de navegador
    ni la regresión.

## F6.4 · Contenido preventivo

Implementado en `entrenamiento-ML` (24/11/2026). Etiqueta previa: `antes-f6-4`.

- **Pantalla** (`components/AdminPrevention.jsx` + `AdminPrevention.css`, `Contenido.dc.html`).
  Sólo presentación, con `AdminUI`:
  - encabezado con ruta y «Nueva sección» (antes estaba en la lista);
  - lista de secciones en tarjeta, con insignias de estado (ícono y el mismo texto de estado);
  - editor en tarjeta con estado y «Última publicación … por …»;
  - campos y «Vista previa del borrador» lado a lado (desde 1200 px), y barra de acciones
    (Publicar, Guardar borrador, Despublicar a la derecha);
  - confirmación en la paleta dorada e historial en su propia tarjeta;
  - en pantallas apiladas (< 1000 px) las secciones son una fila de pestañas con desplazamiento
    horizontal, sin partirse en dos líneas.

  Mismas peticiones, flujo de borrador y publicación, validaciones, historial y textos. La página
  pública no cambia: la vista previa usa los mismos componentes (`RestrictedMarkdown`,
  `SectionSource`).
- **Diferencias deliberadas con la maqueta**:
  - Se conservan los rótulos y textos reales:
    - «Contenido», no «Texto»;
    - «Fuente o referencia sanitaria», no «Fuente sanitaria»;
    - la ayuda de formato completa, con el contador de caracteres;
    - «Vista previa del borrador», no «Vista previa pública»;
    - «Historial», no «Historial de esta sección»;
    - el subtítulo actual;
    - «Publicar» sin «…».
  - Se conservan los campos «Orden» e «Identificador» (este último sólo al crear), que la maqueta
    no muestra.
  - Estados reales: «Publicada · v*N*», «Publicada · cambios sin publicar», «Borrador» y
    «Despublicada · borrador», en lugar de «Publicada», «Cambios sin publicar» y «Despublicada».
    La lista agrega el identificador y el orden.
  - El historial conserva lo que registra la API: acción, autor, fecha y hora, campos cambiados y
    versión publicada. No hay entrada «Creada por» aparte: la carga inicial figura como «Carga
    inicial».
  - Se mantiene la confirmación antes de publicar o despublicar, y el aviso «Guardá el borrador
    antes de publicar».
- **Pruebas**:
  - `test:prevention:browser` pasa cambiando sólo el selector de la línea de estado
    (`.prevention-state`).
  - Nueva `test:content:layout:browser` (demo con SQLite descartable). Cubre lista, edición,
    borrador con cambios sin publicar, nueva sección publicada y error de API, en 1440 y 390 px,
    con contraste AA, teclado, 44 px, textos de 14 px o más y pestañas en una fila con
    desplazamiento.
  - La misma prueba compara la sección recién publicada con el sitio público: mismo título, texto y
    fuente que la vista previa (el sitio agrega « · versión 1»).
  - La prueba no usa interceptación salvo en el estado de error, que es un GET (ver
    «Estabilidad»).
  - Capturas en `data/interim/official/ux-admin-v2-f6-4/<etiqueta>/`: antes en `f6-4-antes`,
    después en `f6-4-regresion`.
- **Rendimiento**: no se midió; la pantalla no toca el servidor ni el visor.

## F6.5 · Pestañas de Alertas en móvil y Cuentas

Implementado en `entrenamiento-ML` (25/11/2026). Etiqueta previa: `antes-f6-5`.

- **Paso 1 · Alertas internas en móvil**:
  - Las pestañas (Pendientes, Reglas, Historial, Cómo funciona) quedan en una sola fila con
    desplazamiento horizontal, como las secciones de Contenido preventivo.
  - El subrayado de la pestaña activa queda dentro de cada pestaña.
  - `test:alerts:layout:browser` lo comprueba: una fila, desplazable y con subrayado visible.
  - Capturas: antes en `ux-admin-v2-f6-2/estab-regresion-2`, después en
    `ux-admin-v2-f6-2/f6-5-regresion`.
- **Corridas de diagnóstico fuera de `data/`**:
  - Con `SIGARD_DIAG_PHASE=<fase>`, los arneses escriben en `frontend/.tmp/diag/<fase>/`, que Git
    ignora.
  - `data/` queda sólo para la evidencia final: `-antes`, `-regresion`, `-regresion-real` y
    `-rendimiento`.
- **Pantalla Cuentas** (`components/AdminAccounts.jsx` + `AdminAccounts.css`, `Cuentas.dc.html`).
  Sólo presentación, con `AdminUI`:
  - encabezado con ruta y «Crear cuenta» (antes estaba en la lista);
  - la política de cuentas como aviso;
  - tabla con correo (con «Tu cuenta»), estado (insignia con ícono «Activa» o «Inactiva»), fecha
    de alta real (`created_at`) y acciones. En móvil, cada cuenta es una tarjeta;
  - tarjeta de operación con el aviso de invalidación de sesiones (dorado para cambiar la
    contraseña, rojo para desactivar), la contraseña actual y la casilla de confirmación explícita
    (toda la línea es un objetivo de 44 px);
  - botones deshabilitados con contraste AA (antes usaban opacidad).

  Mismas peticiones, validaciones, protección del último administrador (botón deshabilitado y la
  API responde 409), límites, auditoría y textos. Ninguna contraseña se muestra, se precarga ni
  queda en el formulario después de una petición.
- **Diferencias deliberadas con la maqueta**:
  - **Reactivación**: la API no tiene un endpoint para reactivar cuentas y no se agregó. Una cuenta
    inactiva muestra «Sin acciones», como la fila «Desactivada» de la maqueta.
  - **«Último cambio»**: ese dato no existe en la API; se muestra «Creada» con la fecha de alta
    real. Tampoco se muestra un último acceso.
  - **Alta**: se conserva el flujo actual. «Crear cuenta» abre la tarjeta de operación con
    contraseña nueva, su confirmación, tu contraseña actual y la casilla de confirmación. La
    maqueta muestra un formulario de alta siempre visible, sin confirmación de la contraseña nueva
    ni casilla.
  - **Textos**: se conservan los reales. El título es «Cuentas administrativas» y el subtítulo el
    actual. La política dice «Cada cambio requiere tu contraseña actual y una confirmación. Debe
    quedar al menos una cuenta administrativa activa.». Los botones son «Rotar contraseña» (no
    «Cambiar» ni «Asignar contraseña»), «Desactivar» y «Crear cuenta administrativa».
  - Estados «Activa» e «Inactiva», no «Desactivada».
- **Pruebas**:
  - `test:accounts:browser` (normal e integral) pasa cambiando sólo el selector de la tabla
    (`.ui-table-scroll`).
  - La corrida integral estaba rota desde F3 (`67cbd08`): buscaba en el menú público un enlace a
    `/dashboard`, y desde entonces «Situación actual» apunta a `/` (`/dashboard` quedó como alias
    local). Se actualizó la ruta del menú a `/`; la visita directa a `/dashboard` se mantiene.
  - Nueva `test:accounts:layout:browser`, con API SQLite descartable y Vite propio; no usa
    interceptación salvo en el estado de error. Cubre:
    - lista y alta;
    - cambio de contraseña;
    - desactivación, que no avanza sin la confirmación explícita;
    - cuenta desactivada sin acciones;
    - último administrador bloqueado en la pantalla y en la API (409);
    - error de API;
    - 1440 y 390 px, con contraste AA, teclado, 44 px, textos de 14 px o más y la tabla dentro de su
      tarjeta.
  - En cada captura se comprueba que no haya contraseñas, hashes ni token en el DOM y que los
    campos de contraseña sean `type=password`.
  - Capturas en `data/interim/official/ux-admin-v2-f6-5/<etiqueta>/`: antes en `f6-5-antes`,
    después en `f6-5-regresion`.
- **Rendimiento**: no se midió; la pantalla no toca el servidor.

## F6.6 · Auditoría

Implementado en `entrenamiento-ML` (25/11/2026). Etiqueta previa: `antes-f6-6`. Sin maqueta: estilo
v2 con `AdminUI` y el criterio visual de Reportes ciudadanos. La propuesta se aprobó antes de
implementar.

- **Endpoint** (`backend/app/admin_audit.py`), `GET /api/v1/admin/audit`, montado sólo por
  `alerts_local` (8767). `app.main` y la demo no lo exponen.
  - **Protección:**
    - control local (cliente loopback, `Host` y `Origin` exactos, sin encabezados reenviados) antes
      del JWT verificado en base (rol, cuenta activa, `token_version`);
    - CORS sólo para `http://127.0.0.1:5173`;
    - respuesta sin caché.
  - **Sin escritura:** no hay rutas para modificar ni borrar eventos; cualquier otro método recibe
    405.
  - **Sin importar el visor:** respeta el invariante F2 (sólo `alerts_local` importa
    `predictive_admin`). Lee `predictive_view_audit` por reflexión cuando el visor la creó; sin esa
    tabla, la categoría «visor» queda vacía.
  - **Filtros:** `category`, `action`, `actor_id`, `date_from` y `date_to`, en días de Argentina con
    UTC−3 fijo. `date_to` incluye el día completo.
  - **Orden y paginación:** del más reciente al más antiguo, con `page` y `page_size` (25 por
    defecto, máximo 100).
  - **Resúmenes con listas cerradas:**
    - de los reportes, el código y el estado anterior y nuevo dentro de la lista de estados, y sólo
      los nombres de los campos cambiados;
    - del contenido, la sección, los campos cambiados y la versión;
    - de las alertas, la regla, la semana, el radio, el motivo y si hubo comentario;
    - del visor, la ruta, el período y el radio.
    - Un campo nuevo en una tabla de auditoría no aparece hasta agregarlo explícitamente.
  - **Registro de la consulta:** cada consulta queda en `admin_audit_view` (actor, fecha y filtros;
    nunca resultados) y falla cerrada. La categoría «auditoría» sólo aparece al elegirla.
- **Pantalla** (`pages/AdminAuditoria.jsx`):
  - encabezado con ruta;
  - aviso de privacidad;
  - filtros (categoría, acción, usuario, desde, hasta) que, con la página, se reflejan en la URL;
  - tabla con fecha y hora de Argentina (24 h), categoría con insignia, acción, usuario, objeto y
    detalle; en móvil, tarjetas;
  - paginación de 44 px;
  - estados de carga, vacío y error con «Reintentar».

  En la demo y en producción muestra el aviso del entorno local, sin consultar. Reemplaza el
  marcador «Próximamente». `ScreenHeader` ahora deja el bloque del título en bloque también sin
  acciones a la derecha.
- **Limitaciones documentadas** en `docs/tecnica/arquitectura.md` §6:
  - sin pantalla en un despliegue;
  - ingresos, intentos fallidos y cierres de sesión no auditados;
  - el historial de un reporte se borra con el reporte al vencer la retención;
  - desfase fijo UTC−3.
- **Pruebas**:
  - `backend/tests/test_admin_audit.py`, 12 pruebas: acceso, control local, CORS, sin rutas de
    escritura, sin valores sensibles, listas cerradas, filtros, orden, paginación, un evento a las
    23:30 del día límite, la consulta registrada con falla cerrada, y que `app.main` y la demo no lo
    expongan.
  - `security/admin-audit.test.mjs`, en `test:admin`.
  - `test:audit:layout:browser`: lista, filtros en la URL que se conservan al recargar, página 2,
    vacío, categoría «auditoría», error de API, hora de Argentina, teclado, 1440 y 390 px, AA, 44 px,
    textos de 14 px o más, sin secretos en el DOM, y la demo con el aviso.
  - `test:admin:browser`: la sección ya no es «Próximamente».
  - Capturas en `data/interim/official/ux-admin-v2-f6-6/`: antes en `f6-6-antes`, después en
    `f6-6-regresion`.

## Cierre F6

Regresión y rendimiento sobre `6db3b5e`, etiqueta `cierre-f6` (25/11/2026), sin cambios de código.
Evidencia en `data/interim/official/`: capturas en `<carpeta de cada suite>/cierre-f6-regresion[-real]/`,
rendimiento en `performance-v1/production/cierre-f6-rendimiento-{1,2,3}/`, resumen en
`cierre-f6-resumen/`; registros de cada suite en `frontend/.tmp/diag/cierre-f6/`.

- **Rápidas** (en verde): lint, build (con el aviso de bloque > 500 kB de siempre), `security:check`,
  `test:guard` 271/271, `test:dev` 28/28 y las suites Node: `test:security` 15, `test:research` 22,
  `test:backtest` 25, `test:public-map` 5, `test:public-activity` 5, `test:citizen` 4,
  `test:prevention` 5, `test:alerts` 5, `test:read-retry` 6, `test:admin` 18, `test:demo` 13
  (151 pruebas, 0 fallos). `git diff --check` limpio.
- **Backend completo** (`publication_isolated.py --backend-regression`): 399 pasan, 6 omitidas
  (requieren un PostgreSQL/PostGIS descartable, que no se inicia).
- **Auditoría de seguridad del repositorio**: 197 controles, 690 archivos versionados, 0 candidatos
  sensibles.
- **Navegador** (21 corridas, todas en verde; Puppeteer existente vía `SIGARD_BROWSER_MODULE`):
  `test:admin:browser` 11 y `--real` 1, `test:admin:home:browser` 5, `test:predictive:browser`
  ficticia y `--real` (0 errores de navegador), `test:predictive:layout:browser` 9,
  `test:predictive-viewer` 3, `test:citizen:browser` 7, `test:prevention:browser` 10,
  `test:alerts:browser` 9 y `--real` 9, y las de layout: alertas 6, reportes 7, contenido 5,
  cuentas 7, auditoría 6. Con `dev` en marcha: `test:accounts:browser` 9 e integral 12 (0
  defectos), `test:public-activity:browser` 11. `test:demo:browser` 11, incluido el cierre con
  Ctrl+C (SQLite y escuchas propias eliminadas). Al terminar cada bloque no quedaban puertos ni
  procesos propios.
- **Rendimiento** (`performance.browser.mjs --target production`, completo, 3 corridas seguidas
  sin otras suites; p95 en ms por corrida, 1 / 5 usuarios):

  | Operación | Corrida 1 | Corrida 2 | Corrida 3 | Mediana |
  |---|---|---|---|---|
  | actividad (fixture) | 384 / 1.193 | 700 / 1.651 | 395 / 1.220 | 395 / 1.220 |
  | prevención | 421 / 1.656 | 563 / 2.419 | 446 / 1.649 | 446 / 1.656 |
  | visor: carga | 1.558 / **7.601** | 1.241 / 4.242 | 1.251 / 4.333 | 1.251 / 4.333 |
  | visor: cambio de semana | 220 / 742 | 363 / 711 | 213 / 716 | 220 / 716 |
  | visor: consulta de radio | 87 / 345 | 120 / 389 | 95 / 283 | 95 / 345 |
  | panel de alertas | 173 / 474 | 151 / 451 | 253 / 452 | 173 / 452 |

  Comparación (cierre F6 = mediana de las 3 corridas):

  | Operación | F0 | F2 | F5 | F6.1 | F6.2 | F6.3 | Cierre F6 |
  |---|---|---|---|---|---|---|---|
  | actividad (fixture) | 604 / 1.146 | 344 / 1.297 | 314 / 1.313 | 390 / 1.281 | 353 / 931 | 305 / 802 | 395 / 1.220 |
  | prevención | 350 / 1.415 | 426 / 1.359 | 326 / 1.312 | 403 / 1.312 | 335 / 1.202 | 307 / 1.065 | 446 / 1.656 |
  | visor: carga | 815 / 2.949 | 1.083 / 3.828 | 1.079 / 4.069 | 1.075 / 3.675 | 917 / 2.905 | 946 / 2.783 | 1.251 / 4.333 |
  | visor: cambio de semana | 180 / 569 | 190 / 826 | 190 / 685 | 171 / 741 | 148 / 514 | 192 / 534 | 220 / 716 |
  | visor: consulta de radio | 81 / 279 | 100 / 350 | 89 / 260 | 82 / 261 | 69 / 221 | 71 / 208 | 95 / 345 |
  | panel de alertas | 174 / 267 | 141 / 428 | 3.677 / 385 | 1.750 / 505 | 143 / 293 | 111 / 362 | 173 / 452 |

  Ninguna mediana supera 5 s. La corrida 1 sí: visor, carga con 5 usuarios, p95 7.601 ms
  (máx. 9.014). La mediana de esa operación (4.333) también supera el presupuesto de F6.1
  (≤ 4.069). Todas las operaciones quedaron más lentas que en F6.3; F6.4–F6.6 no se midieron y,
  según este inventario, no tocan el visor, pero eso no se verificó. Condición de la máquina: durante la corrida 2
  había un juego abierto (≈ 3 GB) y el sistema llegó a memoria crítica; al terminar la corrida 2 ya
  estaba cerrado. No se sabe si estaba abierto en la corrida 1. Causa probable: carga externa de
  la máquina, sin verificar; conviene repetir la medición con la PC libre antes de tomarla como
  referencia.

## F7a · Arreglos técnicos pendientes

Implementado en `entrenamiento-ML` (25/11/2026). Etiqueta previa: `antes-f7`.

- **Puppeteer**: dependencia de desarrollo exacta `25.9.0`; las suites de navegador funcionan sin
  `SIGARD_BROWSER_MODULE`, que queda como override. Instalación y navegador descargado en
  `docs/manuales/manual-instalacion.md` §2.1.
- **Fuentes sin conexión**: IBM Plex Sans (400/500/600/700) e IBM Plex Mono (500/600), estilo
  normal, subconjuntos latin y latin-ext, en `frontend/src/assets/fonts/` con su licencia OFL 1.1 y
  procedencia (`README.md`, SHA-256). Sin Google Fonts ni el ajuste de `dev:demo` que quitaba la
  hoja. Verificado sin conexión (build de producción con todo lo externo bloqueado): antes no había
  ninguna cara cargada (respaldo del sistema); después se cargan las caras locales y no sale ningún
  pedido de fuentes. `test:demo:browser` lo comprueba en la demo.
- **Plurales**: «1 candidata nueva / 2 candidatas nuevas», «1 regla activa evaluada», «N
  inactivas», «N radios sin predicciones suficientes» y «Evidencia de 1 semana»; ningún «(s)» en
  Administración.
- **«Datos hasta —»**: el guion aparece sólo cuando la fuente no tiene semana.
  - Con el visor y el fixture ficticio completo, y con `--real`, la caja muestra la última semana
    evaluable del visor (`test:admin:browser` y su `--real` lo comparan con `/calendar`).
  - Sin visor (Reportes y Cuentas con la API SQLite descartable, demo, producción) muestra la semana
    del manifiesto público (p. ej. «SE 25/2024»).
  - En los entornos de `alerts-layout`, `audit-layout` y `alerts` ficticio (`--source fictional`),
    las rutas del visor responden 503: no hay semana y el guion es correcto.
  - Corregido: un fallo del manifiesto quedaba guardado como «sin semana» hasta recargar la página.
    Ahora sólo se guarda una semana encontrada (`rememberFound`); un fallo se vuelve a pedir en la
    próxima carga (cada sección monta su propio menú). Regresión en `test:admin`.
- **Scripts de navegador sin comando** (decisión de F7a; los dos obsoletos se borraron después, ver «F7a · Limpieza»):
  - `scripts/thesis-workspace.browser.mjs`: **vigente**. No es una suite: es el módulo auxiliar que
    importa `demo-flow.browser.mjs` (`test:demo:browser`) para medir el espacio de análisis de la
    demo. Se ejecuta con esa suite; no lleva comando propio.
  - `scripts/backtest.browser.mjs`: **obsoleto**. Recorre el visor de backtest anterior a F2 contra
    `127.0.0.1:8765/api/v1/research/backtest`; 8765 no existe desde F2 y el visor actual
    (`/api/v1/research/predictive/*` en 8767, con sesión) lo prueba `predictive.browser.mjs`
    (`test:predictive:browser`, también llamado `test:backtest:browser`).
  - `scripts/research-panel.browser.mjs`: **obsoleto**. Su recorrido real necesita la API de
    investigación espacial A/B en `127.0.0.1:8765/api/v1/research/spatial`, que `dev` ya no inicia
    desde F2; su parte ficticia cubre el panel A/B anterior. La ruta a 8765 de
    `services/experimentalResults.js` se retiró en F7b.
- **`npm audit`** (con Puppeteer ya instalado; 12 avisos: 9 altos, 3 moderados). Se aplicó
  `npm audit fix` sin `--force`: `package.json` no cambia (las versiones nuevas caben en los rangos
  declarados), cambia `package-lock.json`. Las dependencias directas suben sólo de versión menor;
  la subida de eslint trae cambios mayores en dependencias transitivas suyas (minimatch 10 → 11,
  keyv 4 → 5, flat-cache 4 → 6, file-entry-cache 8 → 11) y paquetes transitivos nuevos de caché
  (`cacheable`, `hookified` y otros), todos de desarrollo. Después: 4 altos, todos por el mismo
  aviso.

  | Paquete (versión) | Gravedad | Desarrollo / producción | ¿Alcanzable en SIGARD? | Estado |
  |---|---|---|---|---|
  | axios 1.19.0 (12 avisos: contaminación de prototipo, ReDoS, SSRF por redirecciones, HTTP/2) | alta | producción (`dependencies`) | No: ningún archivo de `src` lo importa y no entra al bundle | Corregido: 1.21.1 |
  | follow-redirects 1.16.0 (encabezados con credenciales en redirecciones) | alta | producción (transitiva de axios) | No: sólo el adaptador Node de axios | Corregido: 1.16.3 |
  | vite 8.2.1 (launch-editor en Windows, middleware entre orígenes, `server.fs`) | alta | desarrollo | Sólo el servidor de desarrollo en 127.0.0.1 (`dev`, `dev:demo`, pruebas); no el sitio publicado | Corregido: 8.3.8 |
  | source-map-js 1.2.1 (bloqueo con source maps manipulados) | alta | desarrollo (postcss de vite) | Sólo el build, con source maps propios | Corregido: 1.2.4 |
  | eslint 10.3.0, @eslint/config-array 0.23.5, minimatch 10.2.5, brace-expansion 5.0.9 (DoS con patrones glob) | moderada / alta | desarrollo | Sólo `lint`, con patrones del repositorio | Corregido: eslint 10.15.0, config-array 0.23.6, minimatch 11.0.9, brace-expansion 5.1.0 |
  | zod 4.4.3 (memoria con colecciones grandes) | alta | desarrollo (eslint-plugin-react-hooks) | Sólo `lint`, valida configuración propia | Corregido: 4.6.7 |
  | zod 3.25.76 vía chromium-bidi 17.0.2 → puppeteer-core → puppeteer 25.9.0 | alta (4 avisos encadenados) | desarrollo | No en la práctica: sólo las pruebas de navegador; con Chrome Puppeteer usa CDP, no WebDriver BiDi, y los mensajes vienen del Chromium local | **Pendiente**: la corrección exige puppeteer 25.18.1 y F7a fija 25.9.0 exacto |

  Pendiente aparte (resuelto en «F7a · Integración del remoto y limpieza»): axios figuraba en
  `dependencies` sin usarse.
- **División del bundle por rutas** (opcional): **no se hizo; documentado**. `React.lazy` para
  Administración y el visor obliga a cambiar el contrato de `security/local-entry.test.mjs`
  (`test:research`): esa prueba reemplaza `react` por un sustituto sin `lazy` ni `Suspense` y
  renderiza `App` en forma síncrona con `renderToStaticMarkup`, donde una ruta perezosa sólo
  muestra el respaldo de `Suspense`. Además Leaflet lo usan también el mapa público y Prevención,
  así que seguiría en el bloque principal y no está asegurado que baje de 500 kB. El aviso de Vite
  (bloque principal de unos 642 kB, 194 kB comprimido) sigue y no rompe el build.
- **Pruebas de PostGIS omitidas (6)**: **no se corrieron; documentado**.
  - Cinco están en `backend/tests/test_postgis_integration.py` y se omiten sin `SIGARD_POSTGIS_URL`.
    La sexta, en `test_admin_accounts.py`, se omite sin `SIGARD_TEST_POSTGRES_URL`.
  - Ninguna usa la base de investigación (`sigard_epi_local_v1` ni `sigard_epi_test_v1`, puerto 55439).
    Las define `backend/tests/postgis_disposable.py`: un contenedor **Docker** propio
    (`postgis/postgis:17-3.5`, `sigard-stage17-postgis`, tmpfs) en 127.0.0.1:5435, con las bases
    `sigard_stage16_schema` y `sigard_stage15_test` y el rol `sigard_stage15_test`.
    `postgis_support.validate_url` rechaza cualquier otro destino antes de conectar.
  - No cumplen la condición pedida (sólo la base de prueba `sigard_epi_test_v1`), y correrlas exige
    iniciar Docker, que `AGENTS.md` prohíbe. Ejecutarlas requiere una decisión del responsable:
    autorizar Docker para ese contenedor descartable, o adaptarlas a la base de prueba del clúster
    WSL (55439), lo que exige iniciar WSL/PostgreSQL.
- **Versiones exactas del backend**: `backend/requirements.lock.txt` (`pip freeze` del `.venv`, 44
  paquetes, CPython 3.12.10, Windows x64). Verificado: un venv nuevo instalado sólo desde ese
  archivo da el mismo `pip freeze`, `pip check` sin problemas y la regresión del backend igual (399
  pasan, 6 omitidas). Uso y regeneración en `docs/manuales/manual-instalacion.md` §2.2.
- **Regresión F7a** (25/11/2026, después de todos los puntos, sin `SIGARD_BROWSER_MODULE`; sin
  medición de rendimiento). Todo en verde:
  - **Rápidas**: lint, build (aviso de bloque > 500 kB, ver punto 8), `security:check`,
    `test:guard` 271/271, `test:dev` 29/29 y las suites Node: `test:security` 15, `test:research` 22,
    `test:backtest` 25, `test:public-map` 5, `test:public-activity` 5, `test:citizen` 4,
    `test:prevention` 5, `test:alerts` 5, `test:read-retry` 6, `test:admin` 19, `test:demo` 13
    (153 pruebas, 0 fallos). `git diff --check` limpio.
  - **Backend completo**: 399 pasan, 6 omitidas (PostGIS en Docker, ver arriba).
  - **Auditoría de seguridad del repositorio**: 197 controles, 707 archivos versionados, 0 candidatos
    sensibles.
  - **Navegador** (21 corridas): `test:admin:browser` 11 y `--real` 1, `test:admin:home:browser` 5,
    `test:predictive:browser` ficticia y `--real` (0 errores, las 6 caras IBM Plex locales cargadas,
    ningún pedido a Google Fonts), `test:predictive:layout:browser` 9, `test:predictive-viewer` 3,
    `test:citizen:browser` 7, `test:prevention:browser` 10, `test:alerts:browser` 9 y `--real` 9, y
    las de layout: alertas 6, reportes 7, contenido 5, cuentas 7, auditoría 6. Con `dev` en marcha:
    `test:accounts:browser` 9 e integral 12 (0 defectos), `test:public-activity:browser` 11.
    `test:demo:browser` 11, con las fuentes locales sin conexión y el cierre con Ctrl+C (SQLite y
    escuchas propias eliminadas). Al terminar no quedaban puertos ni procesos propios.
  - Evidencia: capturas en `<carpeta de cada suite>/f7a-regresion[-real]/` y resumen (auditorías npm,
    fuentes sin conexión antes/después) en `data/interim/official/f7a-resumen/`; registros en
    `frontend/.tmp/diag/f7a/`.

## F7a · Integración del remoto y limpieza

- **Merge** de `origin/entrenamiento-ML` (`01c4074`, Referer de los tiles de OSM): las cuatro capas
  de tiles (`BacktestMaps`, `PublicActivity`, `HealthFacilitiesMap`, `CitizenReportForm`) usan
  `referrerPolicy="strict-origin"`, que sólo envía el origen (`http://127.0.0.1:5173/` en local; el
  dominio en producción) y nunca la ruta ni la consulta (`anio`, `se`, `radio`). El resto del sitio
  sigue con `Referrer-Policy: no-referrer` (`frontend/vercel.json`). `test:public-map` exige ese
  atributo en las cuatro capas y `test:predictive:browser` compara el Referer de cada pedido de tile
  con el origen exacto (además, la URL del tile no lleva consulta ni fragmento).
- **Limpieza**:
  - Se quitó `axios` de `dependencies` (no lo importaba ningún archivo; con él salen axios y
    sus dependencias, incluida follow-redirects, del lockfile).
  - Se borraron `scripts/backtest.browser.mjs` y `scripts/research-panel.browser.mjs` (dependían de
    8765). Antes se comprobó que nada los importa; sólo los citaban documentos. `frontend/README.md`
    se actualizó; los documentos históricos (`docs/database/historical-backtesting-stage3.md`,
    `docs/mvp-functional-status.md`, `docs/experimental-spatial-date-query.md`) conservan la mención
    como registro de su etapa.
  - **No** se borró `services/experimentalResults.js`: la búsqueda mostró que lo importan 9 archivos
    de `src` (`App.jsx`, `AdminLayout`, `AdminAlerts`, `AdminInicio`, `AdminAuditoria`,
    `AdminPredictivo`, `backtestResults.js`, `ExperimentalSpatial`, `ExperimentalAnalysis`) y 3
    pruebas: su `localResearchEnabled()` es la compuerta del entorno local. Lo único sin uso
    operativo son sus llamadas a 8765 (`researchCatalog`, `researchDate`, `researchDateQuery`,
    `researchEvaluation`, `researchHistory`), usadas por `ExperimentalSpatial` y
    `ExperimentalAnalysis`; se separaron en F7b (ver abajo).
  - Zod 3 vía Puppeteer queda como se documentó en el punto 7a.

## F7b · Código muerto del panel A/B

- `localResearchEnabled()` pasa a `src/services/localResearch.js` (misma compuerta: `DEV`, origen
  exacto `http://127.0.0.1:5173` y nunca en la demo). Lo importan `App.jsx`, `AdminLayout`,
  `AdminAlerts`, `AdminInicio`, `AdminAuditoria`, `AdminPredictivo` y `backtestResults.js`.
- `ExperimentalSpatial.jsx` y `ExperimentalAnalysis.jsx` no eran alcanzables: ninguna ruta de
  `App.jsx`, página ni enlace los importaba desde F3 (sólo dos pruebas y un reemplazo de
  `local-entry.test.mjs`). La búsqueda amplia (con y sin extensión, `research/spatial`,
  `X-Sigard-Research`, `8765`) no encontró otros usos en `src`, `scripts` ni configuración. Se
  borraron junto con `services/experimentalResults.js`, que tenía las únicas llamadas del frontend
  a `127.0.0.1:8765`.
- Pruebas: se quitaron las dos pruebas que renderizaban esos componentes y la del servicio a 8765;
  se conservan los validadores de contrato (`experimentalContract.mjs`, `experimentalAnalysis.mjs`),
  que siguen usando `SigardComponents` y la regresión backend (`test_experimental_results.py`).
  `local-entry.test.mjs` agrega una prueba que recorre `src/` y falla si reaparece 8765,
  `research/spatial` o los componentes borrados.
- Las menciones en documentos históricos (`docs/mvp-functional-status.md`, `docs/technical-consolidation.md`,
  `docs/experimental-spatial-local.md`) quedan como registro de su etapa.

## F7b · Cierre técnico y documentación

Implementado en `entrenamiento-ML` (25/11/2026). Etiqueta previa: `antes-f7b`. Un commit por punto:
código muerto (arriba), capturas de manuales, README, kit de aceptación v1.0.0,
`docs/tecnica/limitaciones.md`, notas de versión `docs/versiones/v1.0.0.md`. La lista de limpieza
de `data/interim/official/` se entregó en el chat (sólo lectura; no se borró nada).

- **Capturas de manuales**: 16 reemplazadas y 2 nuevas (`admin-inicio.png`, `admin-auditoria.png`),
  todas de corridas con fixtures ficticias (regresión `f7b-regresion` y corridas de las suites de
  layout, alertas, ciudadanía y actividad con `SIGARD_DIAG_PHASE=f7b`); ninguna de corridas `--real`.
- **Regresión F7b** (sin medición de rendimiento; sin `SIGARD_BROWSER_MODULE`). Todo en verde:
  - **Rápidas** (repetidas sobre el HEAD final): lint, build (aviso de bloque > 500 kB),
    `security:check`, `test:guard` 271/271, `test:dev` 29/29, suites Node 123/123
    (`security/*.test.mjs` + `test:demo`).
  - **Backend completo**: 399 pasan, 6 omitidas (PostGIS). Una primera corrida dio 398 + 7 porque
    `test_local_launcher_process_serves_the_viewer_behind_login` se omite si 8767 está ocupado (corría
    en paralelo con las suites de navegador); repetida con los puertos libres.
  - **Auditoría de seguridad**: 197 comprobaciones, 708 archivos versionados, 0 candidatos sensibles;
    `git diff --check` limpio.
  - **Navegador** (en serie): `test:predictive:browser` ficticio (159 pedidos de teselas revisados,
    0 errores) y `--real` (147, 0 errores); `test:predictive:layout:browser` 9 comprobaciones;
    `test:admin:browser` 11; `test:admin:home:browser` 5; `test:demo:browser` 11, con cierre por
    Ctrl+C (SQLite y escuchas propias eliminadas). Además, para las capturas: layout de alertas,
    reportes, contenido, cuentas y auditoría, `test:alerts:browser`, `test:citizen:browser` y
    `test:public-activity:browser` (11), todas con código 0.
