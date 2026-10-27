# Frontend de SIGARD v1.0 académica

Cierre funcional para tesis: `npm.cmd run dev:demo` inicia una demostración
ficticia integral con SQLite descartable; `npm.cmd run dev` conserva el entorno
privado A/B. Abrir `http://127.0.0.1:5173/`. **Ctrl+C** elimina la base temporal
de demo. No habilita operación sanitaria ni promueve ML frente a persistencia.
Ver [cierre, matriz de requisitos y aceptación](../docs/cierre-funcional-tesis.md).
Para otro equipo, seguir la [instalación de la demo desde un clon](../docs/publication-and-demo.md).

SPA React/Vite con dos dominios visuales explícitamente separados:

- vigilancia epidemiológica experimental: `/`, `/mapa`, `/validacion` y
  `/metodologia`;
- prevención y servicios ciudadanos: `/prevencion`;
- operación privada de reportes: `/admin/reportes`.

Las vistas epidemiológicas consultan la API pública configurada mediante
`VITE_API_URL`. Durante la Iteración 11 conservan los contratos de
`public/data/` como respaldo local explícito cuando la API no está disponible.
El pie de la aplicación identifica cuál de las dos fuentes técnicas se utilizó.

## Desarrollo

Desde la raíz del repositorio, instalar las dependencias del frontend una vez:

```powershell
npm.cmd --prefix frontend ci
```

Se utiliza el entorno Python existente en `backend/.venv`, con las dependencias
de `backend/requirements.research.txt`. Si todavía no existe:

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.research.txt
```

Iniciar ambos servicios con un solo comando desde la raíz:

```powershell
npm.cmd --prefix frontend run dev
```

Desde `frontend/` también se puede ejecutar `npm.cmd run dev`.
El coordinador `scripts/dev.mjs` reutiliza `app.research_local` para iniciar
FastAPI en **127.0.0.1:8765** y la configuración existente de Vite para servir
React en **127.0.0.1:5173**. Abrir **http://127.0.0.1:5173**: en desarrollo
local autorizado, `/` redirige a `/mapa` con **Investigación local A/B**
seleccionada. **MVP sintético y contexto** permite volver manualmente a la
simulación original; **Situación actual** abre el dashboard en `/dashboard`.
En producción, `/` conserva el dashboard y `/mapa` inicia en el MVP original.
No requiere Docker ni PostgreSQL.

Si ya existe una API en 8765, se verifica su catálogo, versión de contrato y
restricción de acceso local antes de reutilizarla. Esa instancia permanece
activa al salir. **Ctrl+C** cierra Vite y únicamente el árbol de procesos Python
iniciado por el coordinador. Un servicio incompatible en 8765 o cualquier
ocupación de 5173 bloquea el inicio con un mensaje; no se detienen procesos
ajenos ni se cambia de puerto. No se admiten argumentos para cambiar host/puerto.

Los artefactos A/B y el registro privado deben existir y superar las
validaciones del launcher; no se crean ni reparan automáticamente. Si falta el
entorno o una dependencia, el inicio falla y muestra el motivo. La API de
reportes ciudadanos y administración del puerto 8000 sigue siendo independiente.
Este comando sólo coordina desarrollo: build, preview y producción conservan
su comportamiento. Ver también la [guía experimental](../docs/experimental-spatial-local.md).

### Demostración integral descartable

Desde `frontend/`:

```powershell
npm run dev:demo
```

Desde la raíz: `npm.cmd --prefix frontend run dev:demo`. Requiere las mismas
dependencias del inicio habitual; no instala otras ni modifica producción.
Coordina Vite **127.0.0.1:5173** y FastAPI ciudadana/administrativa en
**127.0.0.1:8766**, con SQLite temporal propia. Comprueba requisitos y puertos;
no reutiliza 8766 ni detiene servicios desconocidos. **No inicia ni consulta A/B**.
`npm run dev` conserva el entorno privado Vite + A/B en 8765.

Abrir **http://127.0.0.1:5173/**. La franja **Demo integral** enlaza al reporte y
seguimiento en `/prevencion` y a `/admin/reportes`. El usuario y la contraseña
de administrador se generan nuevamente por sesión y se muestran una sola vez
en la terminal local. Copiarlos al login sin guardarlos, fotografiarlos ni
incluirlos en grabaciones/informes. No hay contraseña predeterminada ni acceso
sin autenticación; se mantienen permisos, revocación y límites existentes.

El proceso `app/demo_local.py` reutiliza `app.main`, modelos y contratos de la
fixture SQLite existente; no crea otro circuito de reportes. Arranca con Python
aislado, configuración sólo por parámetros internos, sin leer `.env`, secretos
guardados o `DATABASE_URL` heredada. Un guard rechaza otros drivers/archivos antes
de crear el engine y otro impide conexiones SQLAlchemy ajenas al SQLite propio.
No conecta a PostgreSQL. La base comienza vacía, con una sola cuenta inventada,
en `backend/.tmp/sigard-demo-*/demo.sqlite3`, excluida de Git.

Sólo este coordinador activa la marca interna de demo y la URL ciudadana 8766.
El MVP/contexto usa directamente el respaldo estático aprobado, sin consultar
otra API pública. A/B permanece fuera de esta demostración, sin modificaciones.
Los reportes no alimentan modelos ni aparecen en el mapa A/B. Los centros de
salud conservan sus fuentes/límites de vigencia y son contexto público, no datos
ficticios. No se cargan modelos serializados ni se recalculan scores/métricas.

La demo deshabilita geocodificación y geolocalización; elegí un punto manual
ficticio con clic o Tab/flechas/Enter sobre el mapa. El servidor también bloquea
la ruta del geocodificador. Se omiten teselas y la fuente tipográfica remotas
únicamente durante esta sesión; polígonos, marcadores, listado y selector manual
funcionan sin Internet. Los enlaces externos voluntarios conservan sus destinos.

**Recorrido:** mapa público aprobado → prevención/directorio → reporte inventado
→ seguimiento → login en Administración → **Análisis y alertas demo**.
La consulta permite fecha, radio D01–D06, horizonte t+1/t+2/t+4 y persistencia;
la opción V3 usa valores ficticios del contrato, nunca ejecuta V3 real.
Probabilidad validada y superioridad ML siguen pendientes. Una fecha de 2026
devuelve datos insuficientes. Los seis rectángulos son ajenos a La Rioja.

**Ingestión ficticia** valida/carga 48 claves del ejemplo CSV (vacío = desconocido)
y rechaza campos adicionales. **Alertas experimentales** permite crear/editar
reglas, habilitarlas/deshabilitarlas, evaluar manualmente por fecha/horizonte y
marcar candidatas revisadas. Hay auditoría en SQLite, sin notificaciones ni
publicación oficial. Todo requiere rol administrador verificado por el servidor.
Volver a reportes permite revisar/actualizar el reporte; el seguimiento público
nunca revela notas, descripción o coordenadas exactas.

**Ctrl+C** cierra los procesos propios, espera al cierre de SQLite y elimina su
directorio, también ante fallos de inicio. Una API A/B preexistente
permanece intacta porque la demo no la consulta ni controla. Al reiniciar cambian cuenta, contraseña y clave de tokens; los
reportes anteriores no existen. La eliminación se garantiza en el cierre
coordinado; una caída del sistema o terminación forzada del coordinador puede
dejar un directorio temporal ignorado. Nunca se recupera/reutiliza como sesión.
No abrir dos demos ni ejecutar sus pruebas simultáneamente: comparten puertos.

Pruebas reproducibles, con los puertos libres:

```powershell
npm run test:demo
npm run build
npm run test:demo:browser
```

La prueba de navegador requiere Puppeteer ya disponible (o su ruta en
`SIGARD_BROWSER_MODULE`). Inicia FastAPI/Vite reales con fixtures ficticias;
comprueba navegación, consulta, ingestión, alertas, reportes, seguimiento,
roles, reinicio vacío y preview de producción. No simula respuestas HTTP ni
guarda credenciales o códigos de seguimiento. Conserva capturas públicas o
ficticias y mediciones de respuesta en `frontend/.tmp/thesis-closure-ui/`.
La selección aislada
`backend/tests/demo_isolated.py` prueba configuración hostil, guards SQLite,
autenticación y geocodificador bloqueado. No usa Docker ni evalúa ML.

Copiar `.env.example` a `.env` y configurar `VITE_API_URL` **para el modo habitual
o producción; no es necesario en `dev:demo`**. Para producción, la
SPA puede desplegarse en Vercel y debe apuntar a una API FastAPI servida por
HTTPS. Los datos sanitarios estáticos se cargan desde `public/data/` y se
validan antes de mostrarse. El directorio contiene 24 CAPS públicos y 3
hospitales de referencia; 23 CAPS conservan `vigencia_por_confirmar`, por lo que
no deben interpretarse como atención disponible en tiempo real.

## Verificación

```bash
npm run test:dev
npm run test:research
npm run test:public-map
npm run test:citizen
npm run lint
npm run build
```

El cierre del recorrido ciudadano incluye validación/recuperación del formulario,
código copiable y seguimiento sin resultados obsoletos; la bandeja administrativa
ofrece reintento, filtros restablecibles y exportación de esos resultados. Son
recorridos de la API independiente; el comando habitual de desarrollo no la inicia.

`npm.cmd --prefix frontend run test:citizen:browser` verifica la interfaz real con
la fixture existente `backend/tests/browser_admin_fixture.py`, SQLite descartable
y Vite propio en 5174. Requiere Puppeteer ya instalado, resoluble normalmente o
mediante `SIGARD_BROWSER_MODULE`; no instala dependencias. Rechaza 5174 ocupado,
bloquea A/B/solicitudes externas, no usa PostgreSQL/Docker y cierra sus procesos.
Sólo inyecta fallos/respuestas tardías explícitas sobre datos ficticios; las
operaciones de alta, seguimiento, revisión y CSV llegan al backend real del ensayo.
Recibos/capturas en `frontend/.tmp/citizen-flow/`, sin publicar fixtures. Ver
[estado y límites](../docs/mvp-functional-status.md#mejoras-completadas-del-recorrido-ciudadano-y-administrativo).

En `/mapa`, **Investigación local A/B** se selecciona inicialmente sólo en
desarrollo y con el origen exacto `http://127.0.0.1:5173`, para consultar el panel
**Análisis de modelos**, debajo del mapa. Permite comparar seis métricas
congeladas por partición y consultar qué representa cada una. Seleccionar un
radio en el mapa o en el selector conserva la comparación A/B al cambiar
modelo o semana; **Ver evolución temporal** muestra sus scores ya calculados,
con una tabla desplegable de valores y huecos en semanas sin resultado.
Los identificadores técnicos quedan en un detalle secundario.

**Vista del mapa** permite alternar A, B y **Diferencia B − A**, conservando
semana y radio. La diferencia sólo resta dos scores disponibles y validados:
azul es B menor, ocre B mayor, blanco igualdad y gris ausencia. No se guarda ni
equivale a casos/incidencia/riesgo sanitario. El detalle y el mapa comparten los
scores; las respuestas tardías se descartan. La síntesis de desempeño sigue las
métricas de cada partición, sus direcciones y compromisos, sin un ganador fijo.

Recorrido de navegador del panel, desde la raíz con `npm run dev` ya activo:
`node frontend/scripts/research-panel.browser.mjs`. Requiere Puppeteer existente
(o su ruta en `SIGARD_BROWSER_MODULE`), sin instalar dependencias. Comprueba el
panel real y una pestaña separada con polígonos/scores ficticios, errores,
respuestas tardías, teclado y 1440/390 px. Capturas exclusivamente ficticias y
recibo en `frontend/.tmp/research-panel/`; también verifica preview en 5174 y lo
cierra al terminar. No inicia Docker ni accede a PostgreSQL.

El panel es exclusivo de la API local: no agrega resultados experimentales a
`public/` ni al build estático. Sin métricas autorizadas, muestra su ausencia
y mantiene disponible el mapa. Son scores sin calibración clínica y evaluación
retrospectiva sobre positivos provisionales y negativos asumidos; no casos
confirmados ni evidencia de superioridad de un modelo. Ver alcance, consultas
y límites en la [guía experimental](../docs/experimental-spatial-local.md).

La comprobación visual de etapa 10 cubrió el mapa, los selectores y el panel
en escritorio (1440 px) y móvil (390 px). No sustituye una auditoría de
accesibilidad con lector de pantalla.

En el mapa público, **Consultar un radio censal** permite elegir cualquiera de
los 263 códigos con teclado o clic. El mapa enfoca y marca el radio; el detalle
anuncia sus datos agregados y conserva la selección al cambiar capa o semana,
actualizando los valores. La opción vacía limpia el detalle. Etapa 13 verificó
este recorrido, los estados de error, la navegación y la regresión A/B en
Chromium a 1440 y 390 px. Ver [matriz y evidencias](../docs/mvp-functional-status.md).

En `/admin/reportes`, **Gestionar cuentas** abre el listado protegido de cuentas
administrativas. Permite alta, desactivación y cambio/restablecimiento de
contraseña con confirmación y contraseña del administrador que autoriza. La
última cuenta activa está protegida en el servidor; los cambios propios cierran
la sesión cuando revocan el token. No hay registro público ni recuperación por
correo. Requiere la API habitual y la migración de etapa 14; el inicio local A/B
continúa independiente. Ver el [contrato de cuentas](../backend/README.md#cuentas-administrativas-y-autenticación--etapa-14).

La prueba `npm.cmd --prefix frontend run test:accounts:browser` usa una API y
SQLite descartables, con usuarios ficticios. Requiere Vite activo mediante el
comando habitual y Puppeteer ya disponible; puede indicarse su ruta con
`SIGARD_BROWSER_MODULE`. El script no instala dependencias ni inicia Docker.

Para la revisión integral de etapa 15, con Vite ya activo, usar el mismo harness:

```powershell
$env:SIGARD_INTEGRAL_REVIEW = '1'
$env:SIGARD_EXPECT_STABLE = '1'
npm.cmd --prefix frontend run test:accounts:browser
```

Incluye API pública con SQLite temporal/artefactos aprobados, reporte ciudadano
ficticio y seguimiento, revisión/exportación administrativa, rechazos de sesión,
cuentas, A/B y comprobaciones limitadas del árbol accesible de Chromium y contraste.
No sustituye PostGIS, lector de pantalla ni móvil físico. Los recibos y capturas
quedan en `.tmp/stage15-*`; no se incorporan al frontend público. El formulario
permite marcar el centro del mapa con Enter tras desplazarlo con flechas. Las
vistas territoriales compartidas mantienen zoom sin transición animada para
evitar el error de Leaflet al desmontar durante una navegación rápida.

En etapa 16 se comprobó el arranque nuevo, la navegación pública con respaldo
estático, el ciclo ficticio HTTP/SQLite y A/B. Las vistas completas con selector
textual excluyen los polígonos de la tabulación para evitar 263 paradas de tooltip;
conservan clic/hover. El harness integral comprueba Tab del mapa al selector.
El [guion académico y checklist](../docs/SIGARD-resumen-desarrollo.md#8-guion-académico-de-siete-minutos)
describe el circuito integrado con `dev:demo`, que prepara la sesión manual
descartable. El harness de cuentas usa su propia API ficticia y limpia al cerrar;
su comprobación SQLite no acredita PostgreSQL/PostGIS.

## Docker local

La imagen multietapa compila con Node y sirve solamente `dist/` mediante Nginx
sin privilegios. Desde la raíz del repositorio:

```powershell
docker compose -f compose.yaml build frontend
docker compose -f compose.yaml up -d --wait frontend
```

La aplicación queda disponible en `http://localhost:5173`. El valor de
`SIGARD_FRONTEND_API_URL` se incorpora al build y es público; nunca debe
contener secretos. El despliegue previsto en Vercel continúa siendo
independiente del contenedor local, de FastAPI y de PostgreSQL.

El formulario nunca solicita identificadores directos. La geolocalización sólo
se activa al pulsar el botón correspondiente y los reportes no se representan
en el mapa epidemiológico. La búsqueda opcional requiere un consentimiento
separado y envía la referencia a la API de SIGARD, que actúa como intermediaria
ante Nominatim/OpenStreetMap sin reenviar la IP del navegador. Si la persona no
quiere compartir esa referencia puede ubicar el marcador manualmente.
## Demostración predictiva privada

La [guía de cierre experimental](../docs/predictive-experimental-demo.md) explica
el mapa Leaflet autocontenido generado desde `local_query --map-output`.
`npm.cmd --prefix frontend run build:predictive-viewer` compila sólo código genérico
en `.tmp`; los datos se incorporan después bajo `data/interim/official`, nunca en
`public` ni en la distribución. Abrir el HTML privado directamente como archivo
local: no necesita servidor y no habilita una ruta pública ni alertas.
