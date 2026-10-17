# Seguridad de versionado y recursos estáticos antes de integrar A/B

Revisión local del 17/10/2026 en `entrenamiento-ML`. Alcance: exclusiones,
comprobaciones de seguridad y documentación. No se cambian pantallas, endpoints,
modelos ni datasets. Ningún archivo sensible se elimina, mueve o publica.

## Controles aplicados

Se conservaron las reglas existentes y se añadieron defensas a `.gitignore`,
`.dockerignore`, `backend/.dockerignore`, `frontend/.dockerignore` y
`ml/.dockerignore` para:

- `.env` y variantes anidadas, claves/certificados, `.npmrc`/`.netrc` y directorios
  convencionales de credenciales de herramientas, además de configuraciones privadas.
  Las plantillas explícitas `.env.example` siguen permitidas.
- Nombres reservados `.private`, `.private.*`, `.private-*`, `_private.*`,
  `private.*` y directorios privados/confidenciales, sin depender del formato.
  Las reglas privadas prevalecen sobre las excepciones para plantillas.
- Excel `.xls*`, incluidos `.xlsx`, `.xlsm` y `.xlsb`; paneles y derivados como
  Parquet/Arrow; modelos serializados y artefactos en subdirectorios. Se cubren
  variantes de mayúsculas también para builders Linux.
- GeoJSON y otros formatos espaciales fuera de las excepciones públicas aprobadas,
  para no incorporar por accidente exportaciones de coordenadas individuales.
- Fuentes y derivados oficiales, autorizaciones/manifiestos privados, cachés,
  salidas de build y almacenamiento local. Código, pruebas ficticias JSON,
  documentación y `official*.example.json` siguen versionables.
- Las ocho skills de `.agents/skills/` y `skills-lock.json` permanecen locales,
  ignorados por Git y Docker. No se reinstalaron ni modificaron.

`frontend/public/` admite únicamente los diez recursos públicos existentes:

```text
favicon.svg
icons.svg
data/available_weeks.json
data/experimental_spatial_history.geojson
data/health_facilities.geojson
data/model_evaluation.json
data/mvp_metadata.json
data/prevention_content.json
data/temporal_predictions.json
data/territorial_context.geojson
```

Las mismas excepciones se comprueban en Git y en los contextos Docker raíz y
frontend. Se reexcluye el contenido de `public/data/` antes de permitir cada
archivo para que una excepción de directorio no admita nuevos derivados.
No se copian A/B a esta lista. Las coordenadas de establecimientos públicos y los
polígonos censales aprobados se conservan; no se confunden con residencias.

## Protección de archivos servidos por el frontend

`.gitignore` y `.dockerignore` no impiden por sí solos que Vite sirva `public/`.
Por eso se añadió exclusivamente una barrera de seguridad de recursos estáticos:

- `frontend/security/public-assets.json`: nombres y SHA-256 de los recursos
  existentes aprobados, sin datos sanitarios nuevos. El hash normaliza CRLF a LF
  para conservar equivalencia entre checkouts Windows y Linux; no modifica fuentes.
- `public-assets.mjs`: rechaza archivos adicionales, reemplazos bajo nombres
  aprobados y enlaces simbólicos; valida fuentes antes de iniciar/build y la
  distribución al finalizar. No aprueba automáticamente recursos nuevos.
- El middleware se instala antes de los servidores estáticos de Vite dev/preview:
  si aparece un archivo no aprobado después del arranque, bloquea las respuestas
  con 503 y un mensaje genérico, sin devolver contenido, nombres ni valores.
- Vite restringe además el acceso al filesystem del frontend y niega patrones
  sensibles. Se comprueba también `dist/` antes de preview y tras el build.
- `frontend/Dockerfile` copia la carpeta de comprobaciones para que el build no
  omita la barrera. No hay dependencias nuevas ni cambios visuales/funcionales.

Actualizar un recurso legítimo exige revisar su procedencia/contenido, actualizar
de manera explícita la lista/hash y repetir los controles. No regenerar el
registro automáticamente desde una carpeta que podría contener datos privados.
Un hash aprobado no certifica por sí solo anonimización de contenido nuevo.

## Verificaciones repetibles

Desde la raíz:

```powershell
.\ml\venv\Scripts\python.exe -B tools/check_repository_security.py
.\ml\venv\Scripts\python.exe -m pytest ml/tests/test_repository_security.py -q -p no:cacheprovider --basetemp ml/.tmp/security_checks_new
git diff --check
```

Desde `frontend/`:

```powershell
npm.cmd run security:check
npm.cmd run test:security
```

La herramienta Python prueba Git mediante su motor real, usando `--no-index`
para comprobar también nombres de archivos ya tracked. Revisa metadatos de los
contextos actuales sin cargar fuentes, y busca firmas evidentes de secretos en
archivos visibles. Ante un candidato tracked/expuesto detiene la comprobación;
no lo borra, mueve ni desversiona. Su evaluador Docker es un subconjunto explícito
de los patrones actuales, con pruebas de precedencia y fallo ante construcciones
no admitidas; no sustituye una certificación de Moby/BuildKit.

Los tests usan rutas ficticias y archivos temporales ficticios. Incluyen una
prueba HTTP real en loopback con Vite dev y otra con preview: un recurso aprobado
responde 200 y un archivo ficticio añadido luego queda bloqueado sin filtrar su
marcador. Se validan también la configuración Vite real, sustituciones de archivo,
enlaces, LF/CRLF y los hooks de build. No se ejecuta entrenamiento ni la suite global.

El precontrol no encontró candidatos sensibles ya seguidos o recursos públicos
inesperados. Los diez recursos coinciden con HEAD, salvo finales de línea
equivalentes de dos archivos. Se registraron hashes de 774 archivos de datos,
artefactos y skills para comprobar su conservación. Evidencia privada:
`data/interim/official/repository_security_v1/`.

Resultado de entrega: 135 pruebas Python y 15 pruebas Node aprobadas, sin fallos
ni omisiones; 178 sondas de exclusión aprobadas, lint focalizado de la
configuración Vite y `git diff --check` aprobados. La última verificación y sus
hashes quedan en `verification_final.private.json` y `delivery_manifest.private.json`
del directorio privado anterior; los recibos intermedios se conservan.

## Archivos de esta tarea

Modificados: las cinco exclusiones; `frontend/vite.config.js`,
`frontend/package.json` y `frontend/Dockerfile` sólo para instalar/ejecutar la
comprobación; `docs/technical-consolidation.md` y
`docs/technical-commit-plan.json` para reflejar la seguridad y las skills locales.

Nuevos: este documento, `tools/check_repository_security.py`,
`ml/tests/test_repository_security.py` y los tres archivos de
`frontend/security/` (registro, guard y pruebas). Los scripts y recibos de auditoría
privados no forman parte de la propuesta de commits.

## Límites que permanecen

- Un archivo confidencial sin marca, fuera de las rutas protegidas y con formato
  indistinguible de código/configuración, necesita revisión de contenido. El
  escaneo es heurístico; no certifica ausencia universal de datos personales.
- No se auditó ni reescribió todo el historial Git ni se inspeccionaron imágenes
  antiguas, bases operativas o despliegues remotos. No hubo build Docker ni envío
  de contexto; los controles sobre contextos fueron locales y estáticos.
- Los bind mounts de Compose no están protegidos por `.dockerignore`: el proceso
  ML autorizado puede leer datos locales. No se iniciaron servicios ni importadores.
- La barrera se aplica al flujo Vite/Docker configurado. Un servidor genérico
  sobre una carpeta arbitraria, una copia manual posterior a `dist/` o un despliegue
  que omita estas comprobaciones requiere controles propios. No desplegar así.
- No usar `git add -f`, cambiar las listas para aceptar datos privados ni considerar
  estos controles autorización para publicar resultados A/B.

El proyecto queda preparado para revisar y organizar commits seguros de código y
documentación, manteniendo datos/modelos/skills locales y sin hacer staging.
La integración y cualquier publicación siguen fuera de esta tarea.

Referencias de configuración:
[Docker, contextos y exclusiones](https://docs.docker.com/build/concepts/context/#dockerignore-files),
[Vite, hooks y middleware](https://vite.dev/guide/api-plugin.html#configureserver),
[Vite, restricciones de filesystem](https://vite.dev/config/server-options.html#server-fs-deny).
