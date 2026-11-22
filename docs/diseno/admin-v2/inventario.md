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
| `/` | `Dashboard` (`SigardComponents`: StatCard, TerritorialMap, TopRadios). En dev redirige a `/admin/predictivo` (F3) | `services/sigardData.js` → `/data/*.json` o `:8000/api/v1/public/{weeks,territorial-context,model-evaluation,metadata,predictions,experimental-spatial-history}` | `test:security`, `test:public-map`, `test:accounts:browser` (`/dashboard`) |
| `/dashboard` (sólo dev) | `Dashboard` | igual que `/` | `test:accounts:browser`, `test:research` (`local-entry`) |
| `/mapa` (siempre público, F3) | `Mapa` (`TemporalControls`, `TerritorialMap`); en dev, enlace «El módulo predictivo está en Administración» y, con sesión de administrador, `/mapa?<estado del visor>` redirige a `/admin/predictivo?…` | `sigardData.js` (`:8000/api/v1/public/*`) | `test:public-map`, `test:research` (`local-entry`), `test:demo:browser`, `test:predictive:browser` |
| `/admin/predictivo` (F3) | `AdminPredictivo` (`AdminLoginForm` sin sesión) → `HistoricalBacktest` (`WeekTimeline`, `SummaryCards`, `BacktestMaps`, `BacktestHistory`, `RadioPanel`, `ModelPerformance`, `MLComparison`, `DataTable`) | `services/backtestResults.js` + `adminSession.mjs` → `127.0.0.1:8767/api/v1/research/predictive/*` con el token de la sesión de Administración (F2/F3) | `test:backtest` (backtest, predictive-view, private-view), `test:predictive:browser` (ficticia y `--real`, entorno propio en modo sesión), `test:dev`; backend `test_predictive_access.py` |
| `/validacion` | `Validacion` (`BacktestChart`) | `sigardData.js` | `test:research` (`local-entry`) |
| `/metodologia` | `Metodologia` | `sigardData.js` | `test:research` (`local-entry`) |
| `/prevencion` (y `*`) | `Prevencion` → `PreventionGuide`, `SymptomsAlert`, `HealthFacilitiesMap`, `RestrictedMarkdown`, `CitizenReportForm`, `ReportConfirmation`, `ReportStatusLookup` | `services/preventionData.js` (`/data/*`), `citizenReports.js` → `/api/v1/public/prevention`, `/api/v1/citizen-reports`, `/citizen-reports/status/{código}`, `/geocoding/address` (`:8000`, o `:8766` en demo) | `test:prevention`, `test:citizen`, `test:citizen:browser`, `test:prevention:browser`, `test:demo:browser` |
| `/actividad` | `Actividad` → `PublicActivity` (el enlace aparece sólo si la API sirve un paquete habilitado) | `services/publicActivity.mjs` → `:8000/api/v1/public/activity` | `test:public-activity`, `test:public-activity:browser` |
| `/admin/reportes` | `AdminReports` (`AdminLoginForm`, bandeja, detalle, exportar CSV, acceso «Módulo predictivo» en dev) | `citizenReports.js` → `/api/v1/admin/session`, `/admin/citizen-reports*`, `/admin/citizen-reports/export.csv` | `test:citizen`, `test:citizen:browser`, `test:accounts:browser`; backend `test_citizen_reports.py`, `test_route_authorization.py` |
| ↳ panel `accounts` | `AdminAccounts` | `/api/v1/admin/users*` (alta, desactivar, contraseña) | `test:accounts:browser`; backend `test_admin_accounts.py` |
| ↳ panel `prevention` | `AdminPrevention` | `/api/v1/admin/prevention*` (borrador, publicar, historial) | `test:prevention`, `test:prevention:browser`; backend `test_prevention_content.py` |
| ↳ panel `alerts` (no demo) | `AdminAlerts` | `/api/v1/admin/alerts*`, `/admin/alerts/candidates/export.csv` (`VITE_API_URL`: `:8000` en producción, `:8767` con `dev`) | `test:alerts`, `test:alerts:browser`; backend `test_internal_alerts.py` |
| ↳ panel `demo` (sólo demo) | `DemoWorkspace` | `:8766/api/v1/admin/demo/*` | `test:demo`, `test:demo:browser` |

Las suites transversales son `test:dev` (orquestación de `dev` y proxy de navegador),
`test:read-retry` (reintentos de lectura) y `test:research` (resultados y análisis
experimentales, entrada local).

## Notas para Administración v2

- Los paneles de Administración son estados internos (`panel`) de `/admin/reportes`; la
  única subruta propia es `/admin/predictivo` (F3). Las maquetas (`Main`, `Predictivo`,
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
