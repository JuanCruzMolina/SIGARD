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
- [ ] Etapa 2: construcción de la imagen `sigard-backend`.
- [ ] Etapa 3: migraciones Alembic como trabajo independiente.
- [ ] Etapa 4: API FastAPI.
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
docker compose -f compose.yaml up -d
docker compose -f compose.yaml ps
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
