# Escenarios de aceptación (versión v1.0.0)

Kit para **una sesión de 30–45 minutos con 2 referentes del Ministerio de Salud** (P01 y P02).
Hay un escenario para el sitio público y uno por cada una de las siete secciones de
Administración. Todos usan el mismo entorno: `npm run dev` con la fixture ficticia de
«Actividad registrada» (ver `preparacion-sesion.md`). Las observaciones se anotan en
`formulario-observaciones.md`.

Reglas comunes:
- Las dos personas están frente a la misma pantalla. En cada escenario **una maneja** (columna
  «Maneja») y la otra observa y puede opinar al final; se alternan para que ambas usen el sistema.
- El moderador lee la consigna textual y entrega la tarjeta impresa. No ayuda salvo bloqueo: tras
  60 s sin avance da **una** pista estándar y el escenario queda «con ayuda».
- El tiempo máximo incluye la lectura de pantalla. Superado, el escenario queda «no completado» y
  se pasa al siguiente.
- Todo lo que se escribe es inventado: ningún nombre, teléfono, dirección ni dato personal real.

| Esc. | Sección | Maneja | Máx. | Depende de |
|---|---|---|---|---|
| E1 | Sitio público (prevención, reporte, seguimiento, actividad registrada) | P01 | 7 min | — |
| E2 | Administración · Inicio | P02 | 3 min | E1 (el reporte nuevo aparece como pendiente) |
| E3 | Administración · Reportes ciudadanos | P01 | 5 min | E1 |
| E4 | Administración · Contenido preventivo | P02 | 5 min | — |
| E5 | Administración · Módulo predictivo | P01 | 6 min | — |
| E6 | Administración · Alertas internas | P02 | 6 min | — |
| E7 | Administración · Cuentas | P01 | 4 min | — |
| E8 | Administración · Auditoría | P02 | 3 min | E3, E4, E6, E7 |
| | **Total de tareas** | | **39 min máx.** (≈ 25 min esperados) | |

Con bienvenida (5 min) y cuestionario (7 min) la sesión entra en 45 minutos. Si el tiempo se
acorta, se omite la segunda parte de E1 (actividad registrada) y E8 se hace sólo como lectura.

---

### E1 — Sitio público: prevención, reporte y seguimiento
**Punto de partida:** `http://127.0.0.1:5173/`, sin sesión.

**Consigna:** «Usted vio agua acumulada en un terreno baldío. Busque qué recomienda el sistema
para evitar criaderos y cuál es el centro de salud más cercano a la plaza principal. Después
envíe un reporte con una ubicación aproximada inventada y consulte en qué estado quedó. Por
último, abra “Actividad registrada” y diga a qué período corresponden esos datos.»

**Pasos esperados:**
1. Menú **Prevención y ayuda** → lee una medida contra criaderos y usa el directorio de centros
   de salud (búsqueda o filtro).
2. **Reportar**: categoría «Agua acumulada», descripción inventada, punto en el mapa, acepta la
   privacidad y envía. Anota el código de seguimiento (en la tarjeta, no en el equipo).
3. **Seguimiento**: ingresa el código y ve el estado «Recibido».
4. Menú **Actividad registrada** → lee el período del banner.

**Qué observar:**
- si encuentra el directorio sin ayuda y entiende la vigencia «por confirmar» de los centros;
- si el formulario le pide algún dato personal (no debería) y cómo elige la ubicación;
- si el seguimiento muestra sólo código, estado, fechas y mensaje (nunca la descripción ni la
  ubicación);
- si interpreta «Actividad registrada» como datos **históricos** y la trama «protegido» como
  «menos de 5 registros u oculto», no como «sin casos». Con la fixture, el aviso «Datos ficticios
  de prueba» está visible.

**Criterio de aceptación:** nombra una medida y un centro de salud, envía el reporte, obtiene el
estado «Recibido» con su código y responde que la actividad registrada **no** refleja la
situación actual.

**Error crítico:** que el seguimiento o cualquier página pública muestre la descripción o la
ubicación del reporte; que la persona entienda «Actividad registrada» como situación actual y el
sistema no lo aclare.

**Pista estándar:** «Busque en el menú superior algo relacionado con prevención; el código del
reporte sirve para consultar su estado.»

### E2 — Inicio: qué requiere atención
**Punto de partida:** sitio público. El moderador entrega la tarjeta con la cuenta de la sesión.

**Consigna:** «Ingrese a Administración con la cuenta de la tarjeta. En la primera pantalla,
diga cuántos reportes ciudadanos esperan revisión y cuál es el pendiente más antiguo.»

**Pasos esperados:** menú **Administración** → ingreso → **Inicio** → lee «Requiere tu
atención» y la tabla «Pendientes».

**Qué observar:**
- si encuentra el ingreso y si el navegador ofrece guardar la contraseña (se rechaza);
- si entiende el menú lateral (Operación / Gestión), los números naranjas y la barra superior
  con el vencimiento de la sesión;
- si lee el rótulo «Prototipo experimental — reconstrucción histórica, no uso operativo».

**Criterio de aceptación:** ingresa, da la cantidad de reportes en «Recibido» igual a la de la
pantalla (incluye el de E1) y nombra el pendiente más antiguo.

**Error crítico:** que las credenciales queden visibles en pantalla o guardadas en el navegador.

**Pista estándar:** «Busque “Administración” en el menú superior.»

### E3 — Reportes ciudadanos
**Consigna:** «Filtre los reportes de “Agua acumulada”, abra el que se envió en el primer
escenario, páselo a “En revisión” con un mensaje público breve y exporte el listado filtrado.»

**Pasos esperados:** menú **Reportes ciudadanos** → filtro de categoría → abre el reporte (por su
código) → estado «En revisión», mensaje público → **Guardar cambios** → **Exportar CSV**.

**Qué observar:**
- si distingue el **mensaje público** (lo ve el ciudadano) de la **nota interna**;
- si comenta que la ubicación exacta sólo se ve en este panel protegido;
- si el número del menú lateral baja al guardar;
- (opcional, P02) volver a consultar el código en el sitio público y ver el mensaje.

**Criterio de aceptación:** filtro aplicado, reporte en «En revisión» con mensaje público y CSV
descargado.

**Error crítico:** copiar la ubicación exacta o la descripción a un canal público; escribir datos
personales en el mensaje público.

**Pista estándar:** «Los filtros están arriba de la lista; la exportación, arriba a la derecha.»

### E4 — Contenido preventivo
**Consigna:** «Agregue una oración a la sección de eliminación de criaderos, mire cómo queda en la
vista previa y publíquela. Después compruebe en el sitio público que el cambio se ve.»

**Pasos esperados:** menú **Contenido preventivo** → elige la sección → edita → **Guardar
borrador** (estado «cambios sin publicar») → **Publicar** → confirma → la versión sube → abre
**Prevención y ayuda** y encuentra la oración.

**Qué observar:**
- si entiende la diferencia entre **borrador** y **publicado**;
- si usa la vista previa;
- si lee la fuente y el enlace sanitario `https://` que exige la publicación;
- si encuentra el **Historial** con su cambio.

**Criterio de aceptación:** la oración aparece en el sitio público, la versión aumentó y el
historial registra la publicación.

**Error crítico:** que lo público cambie antes de publicar.

**Pista estándar:** «En Administración, “Contenido preventivo”; publicar está debajo del editor.»

### E5 — Módulo predictivo
**Consigna:** «Abra el módulo predictivo y vaya a la semana de la tarjeta (una semana de 2024 con
actividad). En “¿Dónde?”, diga cuántos radios estaban priorizados y cuántos de ellos tuvieron
registros. Después abra uno de esos radios y explique qué esperaba cada método y qué ocurrió.»

**Pasos esperados:** menú **Módulo predictivo** → flechas, año o línea de tiempo hasta la
semana → lee las tarjetas de cifras o la lista «Radios priorizados esta semana» → abre un radio
(mapa, selector o lista) → lee el panel del radio.

**Qué observar:**
- si encuentra la semana sin ayuda;
- si entiende que es una **reconstrucción histórica 2021–2024**, no un pronóstico actual, y que
  los modelos dicen «no promovido»;
- si interpreta «Protegido por privacidad (no significa cero)»;
- si abre «¿Qué tan bien funciona el modelo?» o «Cómo leer esta pantalla y limitaciones».
- El observador comprueba que **Opciones avanzadas** dice «Modo de divulgación: protegido» y que
  no existe el selector de valores exactos.

**Criterio de aceptación:** lee las dos cifras igual que la pantalla (tolerancia 0), explica el
panel del radio y menciona que es una reconstrucción histórica.

**Error crítico:** que la pantalla muestre un valor entre 1 y 4 en un radio, o que presente los
resultados como casos confirmados o situación actual sin aclararlo.

**Pista estándar:** «El selector de semana está arriba; los radios priorizados, a la derecha del
mapa.»

### E6 — Alertas internas
**Consigna:** «Cree una regla llamada “Prueba aceptación” que avise cuando un radio tenga al
menos el número de registros esperados de la tarjeta durante 2 semanas seguidas. Calcule cuántas
veces se habría activado y guárdela. Evalúe la semana de la tarjeta y decida sobre una
candidata: apruébela como aviso interno o descártela, con su motivo.»

**Pasos esperados:** menú **Alertas internas** → **Nueva regla** → «¿Cuántos?», umbral (≥ 5),
2 semanas → **Calcular frecuencia histórica** → **Guardar regla** → pestaña **Pendientes** →
**Evaluar semana** → decide sobre una candidata con comentario o motivo → pestaña **Historial**.

**Qué observar:**
- si entiende que la frecuencia es de la reconstrucción 2021–2024 y sirve para elegir el umbral;
- si entiende que aprobar **no publica nada** a la ciudadanía (franja «Ningún algoritmo publica
  alertas»);
- si la evidencia muestra «protegido» para valores menores a 5;
- si encuentra su decisión en el historial. Si la semana no genera candidatas, se registra y se
  usa la semana de reserva de la tarjeta.

**Criterio de aceptación:** regla guardada con los parámetros pedidos, semana evaluada y una
decisión con motivo visible en el historial.

**Error crítico:** una candidata con valores menores a 5 sin proteger, o una aprobación que cambie
algo del sitio público.

**Pista estándar:** «“Nueva regla” está arriba a la derecha; la evaluación, en la pestaña
Pendientes.»

### E7 — Cuentas
**Consigna:** «Cree una cuenta para una persona nueva del equipo con el correo de la tarjeta
(`aceptacion-nueva@example.test`). Después desactívela como si esa persona dejara el equipo.»

**Pasos esperados:** menú **Cuentas** → **Crear cuenta** → correo y contraseña inicial de la
tarjeta → confirma con **su** contraseña → la cuenta aparece «Activa» → **Desactivar** → confirma
→ queda «Inactiva» y «Sin acciones».

**Qué observar:**
- si entiende por qué se pide la contraseña de quien autoriza;
- si nota que la cuenta inactiva no se puede reactivar desde el panel (limitación conocida);
- si la contraseña inicial queda en pantalla después de confirmar (no debería).

**Criterio de aceptación:** cuenta creada y desactivada; la lista muestra su estado correcto.

**Error crítico:** que alguna contraseña quede visible o guardada; desactivar la propia cuenta y
perder el acceso sin aviso.

**Pista estándar:** «“Crear cuenta” está arriba a la derecha; cada fila tiene sus acciones.»

### E8 — Auditoría
**Consigna:** «Busque en la auditoría quién desactivó la cuenta del escenario anterior y cuándo.
Diga también si la auditoría muestra el texto del mensaje que se escribió en el reporte.»

**Pasos esperados:** menú **Auditoría** → filtra por categoría «Cuentas» (o por fecha de hoy) →
lee el evento de desactivación → filtra «Reportes» y abre el cambio del E3.

**Qué observar:**
- si usa los filtros y entiende la hora de Argentina;
- si entiende que de un cambio se ve **qué campos** cambiaron, no su texto;
- si pregunta por eventos que no están (inicios y cierres de sesión no se registran:
  ver `docs/tecnica/limitaciones.md`).

**Criterio de aceptación:** nombra el usuario y la hora de la desactivación y responde que el
texto del mensaje **no** aparece.

**Error crítico:** que la auditoría muestre una contraseña, una nota, un mensaje o una ubicación.

**Pista estándar:** «Use el filtro de categoría de arriba.»

---

## Material impreso

- Una tarjeta por escenario con la consigna. Datos que completa el equipo antes de imprimir:
  - E2: correo de la cuenta de la sesión (la contraseña se entrega aparte, en papel que se
    destruye al terminar);
  - E5: semana de 2024 con actividad (y su año);
  - E6: umbral (≥ 5), semana a evaluar y una semana de reserva;
  - E7: correo `aceptacion-nueva@example.test` y una contraseña inicial inventada.
- `formulario-observaciones.md` impreso (una copia para el observador).
- Cuestionario SUS y de utilidad (`cuestionario-sus.md`), uno por referente.
- Consentimiento (`protocolo.md`), uno por referente.
