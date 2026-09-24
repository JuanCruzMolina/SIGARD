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
- [ ] Etapa 5: retención como trabajo independiente.
- [ ] Etapa 6: frontend local.
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
