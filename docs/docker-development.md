# Docker en SIGARD: guía de desarrollo local

Esta guía registra la arquitectura objetivo y el procedimiento reproducible
para levantar SIGARD en desarrollo. Los servicios se incorporan por etapas y
cada etapa debe quedar validada antes de continuar con la siguiente.

## Conceptos mínimos

- **Imagen:** plantilla inmutable que contiene software y dependencias.
- **Contenedor:** proceso creado a partir de una imagen.
- **Servicio de Compose:** definición de cómo ejecutar uno o más contenedores.
- **Volumen:** almacenamiento persistente cuyo ciclo de vida es independiente
  del contenedor.
- **Healthcheck:** prueba automática usada para determinar si un servicio está
  listo para recibir conexiones.

La arquitectura objetivo usa cuatro imágenes:

1. `postgis/postgis` para PostgreSQL y PostGIS.
2. `sigard-backend` para API, migraciones y retención.
3. `sigard-frontend` para la interfaz local.
4. `sigard-ml` para trabajos offline de preparación, evaluación y predicción.

La imagen `sigard-backend` se reutilizará con comandos distintos. De ella
saldrán el contenedor permanente de la API, el trabajo temporal de migraciones
y el proceso o trabajo programado de retención.

## Orden de implementación

- [x] Etapa 1: base de datos PostgreSQL/PostGIS.
- [x] Etapa 2: construcción de la imagen `sigard-backend`.
- [x] Etapa 3: migraciones Alembic como trabajo independiente.
- [x] Etapa 4: API FastAPI.
- [x] Etapa 5: retención como trabajo independiente.
- [x] Etapa 6: frontend local.
- [ ] Etapa 7: pipeline ML offline.

## Etapa 1: PostgreSQL y PostGIS

### Objetivo

Disponer de una base espacial persistente y saludable antes de conectar la API.
Esta etapa usa la imagen pública `postgis/postgis:17-3.5` y crea el servicio
`database` definido en `compose.yaml`.

### Archivos involucrados

- `compose.yaml`: describe el servicio, el puerto, el volumen y el healthcheck.
- `.env.example`: documenta los nombres de variables requeridas sin secretos.
- `.env`: configuración privada de cada instalación; no se versiona.

### Preparación inicial

Abrir PowerShell y entrar al repositorio:

```powershell
Set-Location C:\Users\usuario\Documents\Proyectos\SIGARD
```

Crear el archivo privado solamente la primera vez:

```powershell
Copy-Item .env.example .env
notepad .env
```

Asignar una contraseña local privada a `SIGARD_DB_PASSWORD`. No copiar el
contenido de `.env` en documentación, incidencias, commits ni capturas.

> No repetir `Copy-Item .env.example .env` después de configurar el archivo:
> podría reemplazar las claves locales.

### Validar la definición

```powershell
docker compose -f compose.yaml config --quiet
```

Este comando interpreta Compose y verifica que estén definidas las variables
requeridas. `--quiet` evita imprimir la configuración resuelta y reduce el
riesgo de mostrar secretos.

Resultado esperado: el comando termina sin mensajes de error.

### Crear e iniciar la base

```powershell
docker compose -f compose.yaml up -d database
```

- `up` crea o actualiza el servicio y lo inicia.
- `-d` lo deja ejecutándose en segundo plano.
- `database` limita la operación a ese servicio.

Durante la primera ejecución Docker descarga la imagen. En ejecuciones
posteriores reutiliza la copia local mientras siga disponible.

### Comprobar el estado

```powershell
docker compose -f compose.yaml ps
```

El servicio debe pasar de `health: starting` a `healthy`. La publicación
`127.0.0.1:5433->5432` significa que:

- desde Windows se accede por `localhost:5433`;
- desde otros contenedores se accede por `database:5432`;
- el puerto no queda publicado en todas las interfaces de red del equipo.

### Verificar PostGIS

```powershell
docker compose -f compose.yaml exec database psql -U sigard -d sigard -c "SELECT postgis_version();"
```

`exec` ejecuta `psql` dentro del contenedor activo. La consulta debe devolver
una versión `3.5`, lo que confirma que PostgreSQL responde y que PostGIS está
disponible.

### Persistencia

Compose crea el volumen con nombre de proyecto
`sigard-lab_database_data`. Los archivos de PostgreSQL viven allí, no dentro
de la capa descartable del contenedor. Para comprobar su existencia:

```powershell
docker volume ls --filter name=sigard-lab
```

Detener los servicios sin borrar la base:

```powershell
docker compose -f compose.yaml down
```

Volver a iniciarlos:

```powershell
docker compose -f compose.yaml up -d database
```

No usar `docker compose down -v` como operación habitual. La opción `-v`
elimina el volumen y, por tanto, los datos locales de PostgreSQL.

### Rutina diaria

Después de abrir Docker Desktop:

```powershell
Set-Location C:\Users\usuario\Documents\Proyectos\SIGARD
docker compose -f compose.yaml up -d database
docker compose -f compose.yaml ps
```

Después de completar y validar la etapa 4, la rutina podrá iniciar también la
API:

```powershell
docker compose -f compose.yaml up -d
```

Para revisar un problema del servicio:

```powershell
docker compose -f compose.yaml logs --tail 100 database
```

No es necesario copiar nuevamente `.env`, descargar manualmente PostGIS ni
crear otra base en cada sesión.

## Criterio para avanzar a la etapa 2

La etapa de base de datos está completa cuando se cumplen estas condiciones:

- Compose valida la configuración.
- El servicio `database` figura como `healthy`.
- La consulta `SELECT postgis_version()` responde correctamente.
- Existe el volumen `sigard-lab_database_data`.
- `.env` permanece ignorado por Git.

Cumplidos esos puntos, el siguiente paso es construir la imagen
`sigard-backend` sin iniciar todavía la API. Después se ejecutarán las
migraciones de la etapa 3. Sólo con el esquema actualizado iniciaremos FastAPI
y verificaremos su conexión real con PostgreSQL en la etapa 4.

## Etapa 2: imagen del backend

### Objetivo

Construir una imagen reproducible que contenga FastAPI, Alembic y el código del
backend. La imagen no contiene datos, secretos, herramientas de ML ni archivos
de pruebas. En las etapas siguientes se reutilizará para ejecutar migraciones,
la API y la retención con comandos diferentes.

### Archivos involucrados

- `backend/Dockerfile`: receta de construcción de la imagen.
- `backend/.dockerignore`: excluye archivos innecesarios o privados del contexto.
- `backend/requirements.runtime.txt`: dependencias requeridas en ejecución.
- `backend/requirements.txt`: agrega herramientas de desarrollo y pruebas.
- `compose.yaml`: asigna a la imagen el nombre `sigard-backend:lab`.

Las dependencias de ML se mantienen fuera de la imagen del backend. Esto evita
acoplar la API al entrenamiento y reduce el tamaño y la superficie de
dependencias del servicio web.

### Lectura del Dockerfile

`FROM python:3.12-slim` selecciona una base pequeña con Python 3.12.

`ENV PYTHONDONTWRITEBYTECODE=1` evita archivos `.pyc` y
`PYTHONUNBUFFERED=1` envía los registros directamente a Docker.

`WORKDIR /app` fija el directorio de trabajo interno. Los `COPY` posteriores
no copian todo el repositorio: sólo las dependencias, la aplicación, las
migraciones y `alembic.ini`.

Las dependencias se copian e instalan antes que el código para aprovechar la
caché de construcción cuando sólo cambia la aplicación.

`USER sigard` hace que Uvicorn se ejecute como un usuario sin privilegios de
administrador dentro del contenedor.

`EXPOSE 8000` documenta el puerto interno. No publica el puerto por sí mismo;
la publicación local se define en `compose.yaml`.

`CMD` es el comando predeterminado de la API. Migraciones y retención podrán
reemplazarlo sin construir imágenes nuevas.

### Validar antes de construir

```powershell
docker compose -f compose.yaml config --quiet
```

### Construir la imagen

```powershell
docker compose -f compose.yaml build backend
```

`build` procesa el Dockerfile y crea `sigard-backend:lab`, pero no inicia el
contenedor de la API.

### Verificar la imagen sin iniciar la API

```powershell
docker image ls sigard-backend:lab
docker run --rm --entrypoint python sigard-backend:lab -c "import fastapi, sqlalchemy, alembic; print('dependencias OK')"
docker run --rm --entrypoint id sigard-backend:lab
```

La segunda orden comprueba las dependencias principales. La tercera debe
mostrar que el usuario activo es `sigard` y no `root`. `--rm` elimina esos
contenedores temporales al finalizar, pero conserva la imagen.

### Criterio para avanzar a la etapa 3

- La construcción termina sin errores.
- `docker image ls` muestra `sigard-backend` con la etiqueta `lab`.
- Las importaciones principales funcionan.
- El usuario de ejecución es `sigard`.
- La API todavía no está iniciada.

Cumplidos esos puntos se añadirá un servicio temporal `migrations`, construido
desde la misma imagen y responsable de ejecutar `alembic upgrade head`.

### Resultado de la validación local

La etapa se verificó el 23 de septiembre de 2026:

- se construyó la imagen `sigard-backend:lab`;
- se importaron correctamente FastAPI, SQLAlchemy y Alembic;
- se importó `app.main`, incluyendo sus rutas;
- se confirmó que `.env`, las pruebas y las librerías de ML no están dentro;
- el proceso se ejecuta como `uid=999(sigard)` y no como `root`;
- sólo `database` permaneció iniciado durante la validación.

La prueba inicial de importación permitió detectar que `httpx` es una
dependencia de ejecución del módulo de geocodificación. Se corrigió su
clasificación antes de cerrar la etapa.

## Etapa 3: migraciones Alembic

### Objetivo

Crear y actualizar el esquema de PostgreSQL mediante un contenedor temporal,
separado de la API. El servicio `migrations` reutiliza
`sigard-backend:lab`, ejecuta `alembic upgrade head` y termina.

### Configuración compartida

`compose.yaml` define la extensión `x-backend-common` con la imagen, la
construcción, el entorno y la dependencia saludable de PostgreSQL. `backend` y
`migrations` reutilizan ese bloque para evitar que sus conexiones diverjan.

El servicio de migraciones pertenece al perfil `tools`. Por eso no se ejecuta
como servicio permanente al usar el `up` cotidiano, pero sí puede invocarse
explícitamente. Usa `restart: "no"`: terminar después de aplicar el esquema es
el comportamiento correcto.

### Comprobaciones previas

Validar Compose y listar los perfiles:

```powershell
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml config --profiles
```

Comprobar la conexión desde el contenedor sin modificar la base:

```powershell
docker compose -f compose.yaml run --rm migrations python -c "from sqlalchemy import create_engine, text; from app.config import get_settings; engine=create_engine(get_settings().database_url); connection=engine.connect(); print(connection.execute(text('SELECT current_database()')).scalar()); connection.close(); engine.dispose()"
```

Generar el SQL sin ejecutarlo:

```powershell
docker compose -f compose.yaml run --rm migrations alembic upgrade head --sql
```

La simulación permite revisar tablas, restricciones, índices y la transacción
antes de modificar PostgreSQL.

### Aplicar la migración

```powershell
docker compose -f compose.yaml run --rm migrations
```

`run` crea un contenedor temporal usando la definición de `migrations`; `--rm`
lo elimina cuando termina. La imagen y el esquema creado en PostgreSQL
permanecen.

### Verificar la versión

```powershell
docker compose -f compose.yaml run --rm migrations alembic current
```

El resultado esperado en esta etapa es:

```text
20260819_01 (head)
```

Volver a ejecutar `docker compose -f compose.yaml run --rm migrations` es
seguro: Alembic consulta `alembic_version` y no repite una revisión ya aplicada.

### Resultado de la validación local

La etapa se verificó el 23 de septiembre de 2026:

- la base estaba vacía de tablas de aplicación antes de migrar;
- PostGIS `3.5.2` estaba disponible;
- se revisó el SQL offline antes de ejecutarlo;
- Alembic registró `20260819_01` como `head`;
- se crearon `usuarios`, `citizen_reports` y `citizen_report_audit`;
- `citizen_reports.geom` es un `POINT` con SRID 4326;
- existe el índice espacial GiST `ix_citizen_reports_geom`;
- una segunda ejecución terminó correctamente sin repetir cambios;
- los contenedores temporales fueron eliminados con `--rm`.

Durante la revisión previa se alinearon el modelo y la migración de `usuarios`:
correo de hasta 150 caracteres, rol de hasta 20 y rol predeterminado `user`.
La creación administrativa continúa asignando `admin` de forma explícita.

### Criterio para avanzar a la etapa 4

- El servicio `migrations` sólo se ejecuta bajo demanda.
- La base se encuentra en la revisión `head`.
- Las tablas, restricciones e índice espacial existen.
- Repetir `upgrade head` no genera modificaciones.
- El contenedor de la API todavía no está iniciado.

Cumplidos esos puntos se puede iniciar `backend`, verificar su healthcheck y
probar una consulta real desde FastAPI hacia PostgreSQL.

## Etapa 4: API FastAPI

### Objetivo

Iniciar la API sólo después de aplicar las migraciones y marcarla como
saludable únicamente cuando pueda consultar el esquema requerido en
PostgreSQL.

### Liveness y readiness

La API ofrece dos comprobaciones diferentes:

- `GET /health` confirma que el proceso HTTP responde.
- `GET /health/ready` consulta las tablas `usuarios` y `citizen_reports`.

Si PostgreSQL no está disponible o falta el esquema, readiness responde `503`
sin exponer el error interno. El healthcheck de Docker usa readiness, por lo
que `healthy` confirma proceso, conexión y esquema; no sólo que Uvicorn abrió
un puerto.

### Pruebas en una etapa Docker separada

El Dockerfile contiene los targets `runtime` y `test`. La imagen desplegable
se construye con `runtime` y no contiene Pytest ni los archivos de pruebas. El
servicio `backend-tests`, bajo el perfil `tools`, construye el target `test` y
se usa exclusivamente para validación:

```powershell
docker compose -f compose.yaml run --rm --build backend-tests
```

La caché de Pytest se desactiva porque las pruebas se ejecutan como el usuario
sin privilegios `sigard`. Las advertencias de deprecación de dependencias se
registran, pero no se ocultan ni convierten en fallos de la aplicación.

### Construir e iniciar la API

```powershell
docker compose -f compose.yaml build backend
docker compose -f compose.yaml up -d --wait --wait-timeout 60 backend
```

`--wait` no devuelve el control hasta que los servicios estén saludables o se
agote el plazo indicado.

### Verificación local

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-RestMethod http://127.0.0.1:8000/
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 100 backend
```

La documentación interactiva de FastAPI queda disponible localmente en
`http://127.0.0.1:8000/docs` y el contrato OpenAPI en
`http://127.0.0.1:8000/openapi.json`.

### Resultado de la validación local

La etapa se verificó el 23 de septiembre de 2026:

- las 11 pruebas del backend pasaron;
- se comprobó el caso positivo de readiness;
- se comprobó que readiness responde `503` cuando falta el esquema;
- `database` y `backend` quedaron `healthy`;
- liveness y readiness respondieron `200`;
- el endpoint raíz informó la versión `0.2.0`;
- OpenAPI respondió `200`;
- se verificaron `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y
  `Referrer-Policy: no-referrer`;
- Uvicorn continuó con el registro de acceso desactivado y no almacenó IP ni
  rutas solicitadas.

### Operación cotidiana

Iniciar base y API:

```powershell
docker compose -f compose.yaml up -d --wait
```

Detener los servicios conservando el volumen:

```powershell
docker compose -f compose.yaml down
```

### Criterio para avanzar a la etapa 5

- La suite de pruebas termina correctamente.
- El contenedor `backend` figura como `healthy`.
- Readiness demuestra acceso al esquema en PostgreSQL.
- La API es accesible sólo mediante `127.0.0.1:8000` en desarrollo.
- Los registros no incluyen accesos HTTP.

Cumplidos esos puntos se puede crear el servicio de retención usando la misma
imagen `sigard-backend:lab`, sin ejecutar la purga dentro del proceso web.

## Etapa 5: retención de reportes ciudadanos

### Objetivo y alcance

Eliminar reportes ciudadanos cuando vence `retention_until`, fuera del proceso
de FastAPI. Esta política no elimina observaciones epidemiológicas,
asignaciones sintéticas, predicciones ni artefactos del pipeline ML.

El plazo usado al crear cada reporte se configura mediante
`SIGARD_REPORT_RETENTION_DAYS` y debe ser un entero mayor o igual que uno. El
valor predeterminado es 180 días. Cambiarlo afecta los reportes nuevos; no
reescribe retroactivamente `retention_until` en registros existentes.

### Servicio temporal

`retention` reutiliza `sigard-backend:lab`, depende únicamente de una base
saludable, pertenece al perfil `tools` y usa `restart: "no"`. No se implementa
un bucle infinito ni un temporizador dentro del contenedor.

Compose ejecuta el trabajo bajo demanda en desarrollo. En producción, un
programador externo debe invocar el mismo contenedor una vez al día y vigilar
su código de salida.

### Simular sin eliminar

```powershell
docker compose -f compose.yaml run --rm retention python -m app.retention --dry-run
```

La salida informa solamente la cantidad de reportes vencidos. No imprime
descripciones, ubicaciones, códigos de seguimiento ni otros datos privados.

### Ejecutar la purga

```powershell
docker compose -f compose.yaml run --rm retention
```

El trabajo elimina en una transacción los reportes cuyo `retention_until` sea
anterior al instante de ejecución, confirma la transacción, libera la conexión
y termina. `--rm` elimina el contenedor temporal.

Las auditorías asociadas al reporte se eliminan por cascada. Si un reporte
vigente señalaba al vencido como posible duplicado, la revisión Alembic
`20260923_02` pone esa referencia en `NULL` mediante `ON DELETE SET NULL`.

### Secuencia segura al desplegar cambios

```powershell
docker compose -f compose.yaml run --rm --build backend-tests
docker compose -f compose.yaml build backend
docker compose -f compose.yaml run --rm migrations
docker compose -f compose.yaml run --rm retention python -m app.retention --dry-run
docker compose -f compose.yaml run --rm retention
```

Las migraciones deben ejecutarse antes de la purga para garantizar que las
reglas de integridad requeridas ya estén activas.

### Resultado de la validación local

La etapa se verificó el 23 de septiembre de 2026:

- las 11 pruebas del backend pasaron;
- la migración incremental se revisó en modo SQL antes de aplicarse;
- Alembic quedó en `20260923_02 (head)`;
- la clave de posibles duplicados quedó con `ON DELETE SET NULL`;
- sobre una base sin vencidos, simulación y purga informaron cero;
- una prueba controlada detectó y eliminó exactamente un reporte vencido;
- conservó el reporte vigente y anuló su referencia al registro eliminado;
- eliminó por cascada la auditoría asociada al reporte vencido;
- todos los registros sintéticos de validación fueron eliminados al finalizar.

### Criterio para avanzar a la etapa 6

- La retención se ejecuta como trabajo temporal y no dentro de FastAPI.
- Existe un modo de simulación no destructivo.
- La migración y las reglas de integridad están en `head`.
- La eliminación conserva reportes no vencidos.
- No quedan contenedores ni datos sintéticos de la validación.

Cumplidos esos puntos se puede contenerizar el frontend local sin acoplarlo a
la ejecución de migraciones, retención o entrenamiento ML.

## Etapa 6: frontend React/Vite

### Objetivo

Construir los archivos estáticos de React en una etapa Node separada y servir
únicamente el resultado con Nginx sin privilegios. El frontend conserva su
capacidad de desplegarse independientemente en Vercel; esta imagen se usa para
integración local y despliegues alternativos.

### Validación previa

Antes de crear la imagen se ejecutó una instalación reproducible y las
comprobaciones disponibles:

```powershell
Set-Location frontend
npm ci
npm run lint
npm run build
```

`npm ci` usa exactamente `package-lock.json`. El proyecto no define todavía
una suite automatizada de pruebas frontend, por lo que lint, build y las
pruebas HTTP de integración son las verificaciones disponibles en esta etapa.

### Construcción multietapa

`frontend/Dockerfile` contiene dos etapas:

1. `node:24-alpine` instala dependencias, ejecuta lint y produce `dist/`.
2. `nginxinc/nginx-unprivileged:1.30.3-alpine` recibe únicamente `dist/` y la
   configuración del servidor.

La imagen final no contiene Node, npm, `node_modules`, código fuente, `.env` ni
herramientas de compilación. Nginx escucha en el puerto interno 8080 como el
usuario sin privilegios `nginx`.

### Variable pública de API

Vite incorpora `VITE_API_URL` durante el build. En Compose se obtiene desde
`SIGARD_FRONTEND_API_URL`, con `http://localhost:8000` como valor local
predeterminado:

```text
SIGARD_FRONTEND_API_URL=http://localhost:8000
```

Una variable `VITE_*` queda visible en el JavaScript descargado por el
navegador y nunca debe contener credenciales. Se usa `localhost`, no
`backend:8000`, porque la solicitud a la API la realiza el navegador fuera de
la red interna de Docker.

### Servidor estático

`frontend/nginx.conf` implementa:

- fallback a `index.html` para las rutas de `BrowserRouter`;
- cabeceras CSP, `nosniff`, `DENY`, `no-referrer` y Permissions Policy;
- compresión para JavaScript, CSS, JSON y GeoJSON;
- endpoint interno `/healthz`;
- registro de acceso desactivado para no persistir IP ni rutas solicitadas.

El puerto se publica sólo en el equipo local:

```text
127.0.0.1:5173 -> frontend:8080
```

### CORS local

FastAPI autoriza explícitamente los dos orígenes locales equivalentes para el
usuario, pero distintos para el navegador:

```text
http://localhost:5173
http://127.0.0.1:5173
```

Se configuran mediante `SIGARD_CORS_ORIGINS`. No se utiliza un comodín.

### Construir e iniciar

```powershell
docker compose -f compose.yaml build frontend
docker compose -f compose.yaml up -d --wait --wait-timeout 60 frontend
```

Compose espera a que `database` y `backend` estén saludables antes de iniciar
el frontend.

### Resultado de la validación local

La etapa se verificó el 23 de septiembre de 2026:

- `npm ci` instaló 167 paquetes y reportó cero vulnerabilidades conocidas;
- lint y build terminaron correctamente dentro y fuera de Docker;
- la imagen `sigard-frontend:lab` se construyó correctamente;
- la imagen final ejecuta como `uid=101(nginx)` y no contiene Node ni npm;
- no se encontraron nombres de secretos ni archivos `.env` en los artefactos;
- `/`, `/mapa`, `/validacion`, `/metodologia`, `/prevencion` y
  `/admin/reportes` respondieron `200` mediante el fallback SPA;
- los datos públicos respondieron correctamente;
- `/healthz` respondió `200`;
- ambos orígenes locales superaron el preflight CORS;
- `database`, `backend` y `frontend` quedaron `healthy`;
- los registros de Nginx no contienen accesos HTTP.

### Criterio para avanzar a la etapa 7

- La compilación es reproducible desde `package-lock.json`.
- La imagen final sólo contiene los artefactos estáticos y Nginx.
- Las rutas directas de la SPA funcionan.
- Frontend, API y base están saludables.
- CORS acepta únicamente los orígenes locales previstos.
- El despliegue del frontend continúa desacoplado de FastAPI y PostgreSQL.

Cumplidos esos puntos se puede diseñar la imagen offline de ML sin incorporar
entrenamiento ni artefactos de modelos al backend.
