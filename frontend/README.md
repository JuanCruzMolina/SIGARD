# Frontend de SIGARD

SPA React 19 + Vite 8 + Leaflet. Se despliega en Vercel como sitio estático; la API FastAPI y las
bases de datos se ejecutan aparte. En el equipo local, `npm run dev` agrega la API administrativa
con el visor predictivo.

Visión general, criterios y documentación: [README del repositorio](../README.md).

## Rutas

| Ruta | Para quién | Qué es |
|---|---|---|
| `/` | Público | Situación actual (dashboard epidemiológico agregado, con su fuente técnica en el pie) |
| `/mapa` | Público | Mapa público agregado por radio censal. Siempre es el mapa público; un enlace viejo `/mapa?…` con estado del visor redirige a `/admin/predictivo?…` sólo con sesión de administrador |
| `/actividad` | Público | «Actividad registrada» con supresión de valores pequeños. Oculta salvo con un paquete autorizado o la fixture ficticia (`SIGARD_PUBLIC_ACTIVITY=fixture`) |
| `/prevencion` | Público | Prevención y ayuda: contenido publicado desde Administración, centros de salud, teléfonos, reporte ciudadano anónimo y seguimiento por código |
| `/validacion`, `/metodologia` | Público | Validación temporal y explicación del método |
| `/admin/*` | Administradores | Siete secciones con menú lateral y barra de sesión (ver abajo) |

Las vistas epidemiológicas consultan la API pública de `VITE_API_URL` y, si no responde, usan el
respaldo estático aprobado de `public/data/`; el pie indica cuál se usó.

## Instalación

Desde la raíz del repositorio:

```powershell
npm.cmd --prefix frontend ci
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
```

- `npm ci` instala también **Puppeteer 25.9.0** (versión exacta, sólo desarrollo) y descarga
  Chrome for Testing 152 en `%USERPROFILE%\.cache\puppeteer\` (≈700 MB, fuera del repositorio).
  Sin conexión: `$env:PUPPETEER_SKIP_DOWNLOAD='true'` y luego
  `node frontend/node_modules/puppeteer/lib/puppeteer/node/cli.js browsers install chrome`.
  `SIGARD_BROWSER_MODULE` permite usar otra instalación de Puppeteer.
- `backend/requirements.lock.txt` fija el entorno Python probado (CPython 3.12, Windows x64). En otro
  sistema operativo, usar `backend/requirements.research.txt`.
- `frontend/.env` (copia de `.env.example`) sólo hace falta para el modo habitual o producción:
  `VITE_API_URL` apunta a la API pública (por defecto `http://localhost:8000`). Se incorpora al
  build y es público: nunca debe contener secretos.

## Levantar el sistema

```powershell
npm.cmd --prefix frontend run dev        # entorno de trabajo
npm.cmd --prefix frontend run dev:demo   # demostración ficticia descartable
```

Abrir siempre **http://127.0.0.1:5173/**. Desde `frontend/` también vale `npm run dev`.

| Puerto (`127.0.0.1`) | Servicio | Comando |
|---|---|---|
| 5173 | Vite (este frontend) | `dev`, `dev:demo` |
| 8767 | API administrativa local (`backend/app/alerts_local.py serve`): sesión, reportes, contenido, cuentas, alertas, auditoría, visor predictivo (`/api/v1/research/predictive/*`) y rutas públicas | `dev` |
| 8766 | API ficticia de la demo con SQLite temporal | `dev:demo` |
| 5174 | Vite propio de algunas pruebas de navegador | pruebas |

- `scripts/dev.mjs` coordina Vite y la API 8767. Si 5173 u 8767 están ocupados, no arranca y lo
  dice; no detiene procesos ajenos ni cambia de puerto. **Ctrl+C** cierra sólo lo que inició.
- La Administración local guarda reportes, contenido, cuentas y alertas en un SQLite privado
  persistente (`data/interim/official/internal-alerts-v1/`, ignorado por Git).
- El visor necesita el paquete histórico final y su registro privado. Si faltan o no pasan la
  verificación SHA-256, la API arranca igual, la terminal lo avisa y el visor responde 503. Si
  existe la historia anual precalculada (`data/interim/official/predictive-history-v1/`), se sirve
  sin recalcular. Ver [módulo predictivo](../docs/predictive-module-final.md).
- `dev` y `dev:demo` comparten 5173: no se ejecutan a la vez. `dev:alerts` es un alias obsoleto de
  `dev`. El puerto 8765 (lector A/B sin autenticación) no existe desde F2.

### Entrar a Administración

1. Con `dev`, crear una vez la cuenta local, en otra terminal (puede ser con `dev` en marcha):
   `.\backend\.venv\Scripts\python.exe -B backend/app/alerts_local.py create-admin`.
   `dev` arranca sin cuenta y muestra ese comando. En `dev:demo` la cuenta se genera en cada inicio
   y se muestra una sola vez en la terminal: copiarla al login sin guardarla.
2. Abrir **Administración** (`/admin`) e ingresar. La sesión dura 60 minutos.

| Sección | Ruta | Contenido |
|---|---|---|
| Inicio | `/admin/inicio` | Pendientes que requieren decisión, estado del sistema, 10 pendientes más antiguos, accesos rápidos |
| Módulo predictivo | `/admin/predictivo` | Reconstrucción 2021–2024: ¿Dónde? (top-10) y ¿Cuántos?, ML no promovido frente a referencia, panel por radio, desempeño por año; modo protegido (< 5 oculto). Sólo en `dev` |
| Alertas internas | `/admin/alertas` | Reglas con frecuencia histórica, evaluación manual, candidatas para aprobar o descartar, historial. Sin publicación ciudadana |
| Reportes ciudadanos | `/admin/reportes` | Bandeja con filtros, detalle protegido, estado, mensaje público, nota interna, CSV |
| Contenido preventivo | `/admin/contenido` | Borrador con vista previa, publicación versionada, despublicación, historial |
| Cuentas | `/admin/cuentas` | Alta, rotación de contraseña, desactivación (sin reactivación; la última activa está protegida) |
| Auditoría | `/admin/auditoria` | Registro de sólo lectura con filtros en la URL; sin contraseñas, textos ni valores del visor. Sólo en `dev` |

En producción (build estático) y en la demo, el visor y la auditoría indican que sólo existen en
el entorno local. Uso detallado: [manual del administrador](../docs/manuales/manual-administrador.md).

### Modo privado del visor

El visor muestra siempre el modo protegido. El selector de valores exactos sólo existe si `dev` se
inicia con `$env:SIGARD_PRIVATE_VIEW='1'`; el build de producción nunca lo incluye y la API aplica
su propia protección. No se usa en demostraciones.

## Demostración integral descartable (`dev:demo`)

Coordina Vite 5173 y FastAPI 8766 (`backend/app/demo_local.py`) con SQLite temporal en
`backend/.tmp/sigard-demo-*/`. Arranca con Python aislado: no lee `.env`, secretos ni
`DATABASE_URL`, y no conecta a PostgreSQL. Comprueba puertos y no reutiliza 8766.

- La franja **Demo integral** enlaza al reporte y al seguimiento en `/prevencion` y a
  `/admin/reportes`. Todo es ficticio: no se cargan resultados privados ni el visor predictivo.
- Sin geocodificación ni geolocalización (el servidor bloquea el geocodificador); el punto se
  elige a mano con clic o con Tab/flechas/Enter. Sin teselas remotas: polígonos, marcadores y
  selector funcionan sin Internet.
- **Ctrl+C** cierra los procesos, espera el cierre de SQLite y borra su directorio. Una caída o un
  cierre forzado pueden dejar un directorio temporal ignorado, que nunca se reutiliza.

## Pruebas

Con los puertos libres (no correr dos suites de navegador ni una demo a la vez):

```powershell
# Rápidas
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run security:check
npm.cmd --prefix frontend run test:guard
npm.cmd --prefix frontend run test:dev
# Suites Node (sin navegador)
npm.cmd --prefix frontend run test:security        # y test:research, test:backtest, test:public-map,
                                                  # test:public-activity, test:citizen, test:prevention,
                                                  # test:alerts, test:read-retry, test:admin, test:demo
# Navegador (Puppeteer, sin ventanas; cada una levanta y cierra su propio entorno)
npm.cmd --prefix frontend run test:predictive:browser          # visor con fixture ficticia ( -- --real: agregados locales)
npm.cmd --prefix frontend run test:predictive:layout:browser
npm.cmd --prefix frontend run test:admin:browser               # y test:admin:home:browser
npm.cmd --prefix frontend run test:demo:browser                # demo completa con cierre
```

Las suites `*-layout` de cada sección (`test:alerts:layout:browser`, `test:reports:layout:browser`,
`test:content:layout:browser`, `test:accounts:layout:browser`, `test:audit:layout:browser`) y las de
recorrido (`test:alerts:browser`, `test:citizen:browser`, `test:prevention:browser`) usan SQLite
descartable y datos ficticios. `test:public-activity:browser` necesita `dev` en marcha.
`test:performance` mide el criterio de respuesta (p95 < 5 s) en desarrollo o, con
`-- --target production`, sobre `vite build` + `vite preview`.

Las capturas van a carpetas privadas ignoradas por Git, una nueva por corrida
(`SIGARD_SHOTS_LABEL`); con `SIGARD_DIAG_PHASE=<fase>` van a `frontend/.tmp/diag/<fase>/`.

## Privacidad del formulario ciudadano

El formulario nunca pide identificadores directos. La geolocalización sólo se activa con su botón
y los reportes no aparecen en ningún mapa público. La búsqueda de dirección es opcional, con
consentimiento aparte, y pasa por la API de SIGARD, que consulta Nominatim/OpenStreetMap sin
reenviar la IP del navegador. Las teselas de OpenStreetMap se piden con
`referrerPolicy="strict-origin"` (sólo viaja el origen); el resto del sitio usa
`Referrer-Policy: no-referrer` (`vercel.json`).

El directorio sanitario (`public/data/`) tiene 24 CAPS y 3 hospitales; 23 CAPS conservan
`vigencia_por_confirmar` y no indican atención disponible en tiempo real.

## Docker local (opcional)

La imagen multietapa compila con Node y sirve sólo `dist/` con Nginx sin privilegios
(`docker compose -f compose.yaml build frontend`). Docker Desktop permanece apagado en el trabajo
habitual del proyecto; el despliegue previsto es Vercel.

## Visor predictivo autocontenido (privado)

`npm.cmd --prefix frontend run build:predictive-viewer` compila sólo código genérico en `.tmp`; los
datos se incorporan después bajo `data/interim/official`, nunca en `public/` ni en la distribución.
Ver [demo predictiva privada](../docs/predictive-experimental-demo.md).

## Histórico

El panel «Investigación local A/B» de `/mapa` (API sin autenticación en 8765) se retiró en F2 y su
código en F7b. Su descripción y la de las etapas 10–16 quedan en
[estado del MVP](../docs/mvp-functional-status.md) y
[cierre funcional](../docs/cierre-funcional-tesis.md).
