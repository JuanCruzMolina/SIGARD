# Módulo 4 · Alertas internas con aprobación humana

Estado al 14/11/2026. Prototipo académico. Las alertas se construyen sobre predicciones
ya integradas (`rf_v2_city_propensity`, `residual_v2`, v1 y la referencia `count_latest`)
en una **reconstrucción retrospectiva 2021–2024**; 2024 ya fue observado. No es un
sistema operativo ni de vigilancia, y **ningún algoritmo publica alertas**.

## Especificación exigida por la tutoría

| Punto | Definición |
|---|---|
| **Canal** | Notificaciones **internas** en el panel del administrador (`/admin/alertas`, ítem «Alertas internas» del menú lateral). Sin correo, SMS, webhooks ni publicación ciudadana automática. |
| **Periodicidad** | Semanal y manual: **el administrador ejecuta la evaluación al recibir la entrega semanal de datos; la automatización queda fuera del alcance del prototipo.** («Evaluar semana X».) |
| **Origen del umbral** | Lo elige el administrador al crear la regla. En ¿Cuántos? el mínimo es **5 registros esperados** (protección de celdas pequeñas). Antes de guardar, la pantalla muestra la «Frecuencia de activación en 2021–2024 (reconstrucción retrospectiva; 2024 ya observado)»; sin ese cálculo para la regla actual no se puede guardar. En ¿Dónde? la condición es fija: el radio queda dentro del top-k del modelo (k=10). |
| **Responsable de aprobación** | Un administrador autenticado (rol `admin`, sesión verificada en base). Aprueba con comentario obligatorio o descarta con motivo (`false_alarm`, `insufficient_context`, `duplicate`, `other`) y detalle. Queda registrado quién y cuándo. |
| **Mitigación de falsas alarmas** | (1) **Semanas consecutivas** (1–4): la condición debe cumplirse en todas las semanas de la ventana; (2) **revisión humana obligatoria**: el algoritmo sólo genera candidatas; (3) **publicación ciudadana bloqueada** en el código (ruta que siempre responde 409 y se audita) y en el esquema (`CHECK` de estado sin estado «publicada»); (4) una ventana con predicciones faltantes o con huecos de calendario nunca genera candidatas. |

## Flujo

Regla → evaluación semanal manual → **alerta candidata** → revisión de un administrador
(aprobar con comentario / descartar con motivo) → **aviso interno aprobado** o descartada
→ historial y auditoría. Publicarla a la ciudadanía está fuera del alcance y bloqueado.

## Reglas

- Radios: todo el territorio común (256) o un conjunto elegido.
- Pregunta y modelo: ¿Dónde? sólo con modelos de regla top-k; ¿Cuántos? con modelos
  de conteo o la referencia `count_latest`. Por defecto, los candidatos v2 del visor.
- Semanas consecutivas 1–4; activa/inactiva (una regla inactiva nunca dispara).
- No se borran: se desactivan. Cada edición incrementa la versión (bloqueo optimista)
  y las candidatas conservan la copia de la regla usada en la evaluación.
- Reevaluar la misma semana no duplica candidatas (única por regla, versión, semana y radio).

## Privacidad

Los valores **esperados y observados menores a 5** (incluido 0) se muestran como
«protegido» en candidatas, evidencia de las N semanas, vista previa histórica,
historial, auditoría y exportación CSV. Motivo: `residual_v2` parte de la persistencia,
por lo que un valor esperado puede revelar casi exactamente un conteo observado. Los
valores exactos sólo existen en la memoria del proceso de alertas (leídos de la API
predictiva en modo privado); en la base se guardan únicamente valores ya protegidos.
En la vista previa, la cantidad de activaciones con registros observados se protege si
ella o su complemento es menor a 5. Mostrar que un radio está en el top-10 está
permitido en este panel interno autenticado.

## Arquitectura y persistencia

- **API administrativa** (`backend/app/internal_alerts.py`, `/api/v1/admin/alerts/*`),
  todas las rutas con `get_current_admin` (401 sin sesión, 403 sin rol). Tablas
  `internal_alert_rules`, `internal_alert_evaluations`, `internal_alert_candidates`,
  `internal_alert_audit` (migración `20261114_06_internal_alerts`).
- **Fuente de predicciones** (`backend/app/alert_source.py`): desde F2 lee, dentro del mismo
  proceso y sin HTTP ni token, el servicio predictivo que la API administrativa local
  (`alerts_local`) abre y sirve al visor sólo con sesión de administrador (modo privado),
  con caché compacto por proceso. `app.main` y los despliegues nunca abren artefactos
  privados: sólo `alerts_local` adjunta la fuente; en un despliegue el módulo responde
  «fuente no disponible» y no evalúa.
- **Lógica compartida** (`backend/app/alert_rules.py`): umbral, ventana de semanas
  consecutivas, protección y bloqueo de publicación. La demo ficticia
  (`demo_workspace.py`) la reutiliza con su contrato sin cambios (ventana de 1 semana).
- **Almacenamiento local**: `npm run dev` usa un SQLite privado persistente en
  `data/interim/official/internal-alerts-v1/alerts.private.sqlite3` (ignorado por Git y
  verificado por `tools/check_repository_security.py`). Usa el esquema ORM, como la demo,
  porque la cadena Alembic completa requiere PostGIS; la migración 06 es el camino para
  instalaciones gestionadas y se prueba aislada en SQLite.

## Ejecución local

`npm run dev` levanta las alertas junto con el resto de la Administración. Arranca aunque no
exista la cuenta y muestra en la terminal el comando para crearla una vez (interactivo; la
contraseña no se muestra ni se guarda en texto), sin reiniciar `dev`:

```powershell
npm.cmd --prefix frontend run dev
.\backend\.venv\Scripts\python.exe -B backend/app/alerts_local.py create-admin   # otra terminal
```

| Comando | Puertos |
|---|---|
| `dev` | 5173 (Vite) · 8767 (API administrativa con alertas y visor predictivo autenticado; desde F2 no hay 8765) |
| `dev:demo` | 5173 · 8766 (API demo ficticia) |
| `dev:alerts` | Obsoleto: alias de `dev` |

`dev` comparte 5173 con `dev:demo`: **no se ejecutan en paralelo**. Los tokens
caducan al detener la API (secreto nuevo por proceso). Al iniciar se precarga el caché de
predicciones (~25 s para 2021–2024).

## Pruebas

- `backend/tests/test_internal_alerts.py` (fuente ficticia generada): reglas inválidas,
  disparo por semanas consecutivas, regla inactiva, candidatas sólo con datos disponibles,
  protección de valores menores a 5 en todas las salidas, aprobación/descarte con auditoría
  y bloqueo optimista, bloqueo de publicación ciudadana, 401/403 en todas las rutas,
  migración arriba/abajo y contrato del cliente de la API predictiva.
- `frontend/security/internal-alerts.test.mjs` (`npm run test:alerts`).
- `npm run test:alerts:browser`: flujo completo con fuente ficticia y SQLite desechable;
  `--real` repite el flujo con la API predictiva local (valores protegidos) sólo para
  capturas privadas en `data/interim/official/ux-internal-alerts-20261114/<etiqueta>/` (carpeta nueva
  por corrida: `SIGARD_SHOTS_LABEL` o fecha y hora; nunca sobrescribe corridas anteriores).

## Límites

- Retrospectivo: la «semana siguiente» ya fue observada; 2025–2026 siguen bloqueados.
- Las candidatas no son alertas epidemiológicas ni casos; ningún modelo está promovido.
- Recorrido con PostgreSQL/PostGIS real pendiente (no se inició Docker).
