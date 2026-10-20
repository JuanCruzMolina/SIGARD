# Frontend de SIGARD

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
React en **127.0.0.1:5173**. Abrir **http://127.0.0.1:5173/mapa** y seleccionar
**Investigación local A/B**. No requiere Docker ni PostgreSQL.

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

Copiar `.env.example` a `.env` y configurar `VITE_API_URL`. Para producción, la
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
npm run lint
npm run build
```

En `/mapa`, seleccionar **Investigación local A/B** para consultar el panel
**Análisis de modelos**, debajo del mapa. Permite comparar seis métricas
congeladas por partición y consultar qué representa cada una. Seleccionar un
radio en el mapa o en el selector conserva la comparación A/B al cambiar
modelo o semana; **Ver evolución temporal** muestra sus scores ya calculados,
con una tabla desplegable de valores y huecos en semanas sin resultado.
Los identificadores técnicos quedan en un detalle secundario.

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
explica qué puede mostrarse con el comando habitual y qué precisa la API separada.
El harness sólo redirige su propio navegador a la API ficticia y limpia al cerrar;
no prepara una sesión administrativa manual ni acredita PostgreSQL/PostGIS.

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
