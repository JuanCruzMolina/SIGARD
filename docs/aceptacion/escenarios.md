# Escenarios de aceptación

Cada tarea se lee textualmente y se entrega impresa. «Entorno» remite a `preparacion-sesion.md`.
Los tiempos máximos incluyen la lectura de pantalla. Superado el máximo, la tarea queda
«no completada».

| Tarea | Módulo | Perfil | Entorno | Máx. |
|---|---|---|---|---|
| E1 | 1 Prevención | Todos | A (`dev:demo`) | 3 min |
| E2 | 2 Reporte ciudadano | Todos | A | 6 min |
| E3 | 6 Administración | Gestión de reportes | A | 2 min |
| E4 | 6 Administración | Gestión de reportes | A | 6 min |
| E5 | 6 Contenido preventivo | Comunicación | A | 7 min |
| E6 | 4 Visor predictivo | Vigilancia | B (`dev`) | 6 min |
| E7 | 4 Visor predictivo | Vigilancia | B | 4 min |
| E8 | 3 Actividad registrada | Todos | C (`dev` + API fixture) | 5 min |
| E9 | 5 Alertas internas | Vigilancia | D (`dev:alerts`) | 8 min |
| E10 | 5 Alertas internas | Vigilancia | D | 4 min |

---

### E1 — Consultar la información de prevención
**Consigna:** «Usted quiere saber qué hacer en su casa para evitar criaderos de mosquitos y
dónde está el centro de salud más cercano a la plaza principal. Encuéntrelo en el sistema.»

**Éxito:**
- abre «Prevención y ayuda»;
- nombra al menos una medida de eliminación de criaderos;
- usa el directorio (búsqueda o filtro) y nombra un centro de salud.

**Pista estándar:** «Busque en el menú superior algo relacionado con prevención.»

### E2 — Enviar un reporte ciudadano y consultar su estado
**Consigna:** «Vio agua acumulada en recipientes en un terreno baldío. Envíe un reporte
(ubicación aproximada inventada, sin datos personales) y luego consulte en qué estado está.»

**Éxito:**
- completa categoría, descripción y ubicación en el mapa;
- acepta la privacidad y envía;
- conserva el código de seguimiento;
- en «Seguimiento» obtiene el estado «Recibido».

**Error crítico:** escribir datos personales reales y que el sistema los muestre públicamente.
Debe registrarse aunque haya sido inducido por la persona.

**Pista estándar:** «El código que le dio el sistema sirve para consultar el estado.»

### E3 — Iniciar sesión como administrador
**Consigna:** «Ingrese al área de administración con la cuenta que le entregamos en papel.»

**Éxito:** llega a «Reportes ciudadanos» con la sesión iniciada. Las credenciales no quedan
visibles en pantalla ni guardadas en el navegador.

**Pista estándar:** «Busque “Administración” en el menú.»

### E4 — Revisar y exportar reportes
**Consigna:** «Filtre los reportes de categoría “agua acumulada”. Abra el que envió en la tarea
E2, cámbielo a “En revisión” con un mensaje público breve y exporte el listado a CSV.»

**Éxito:**
- el filtro está aplicado;
- el reporte cambió a «En revisión» con mensaje público;
- el archivo CSV se descargó.

La persona sabe explicar que la ubicación exacta sólo se ve en el panel protegido. **Error
crítico:** copiar la ubicación exacta a un canal público.

**Pista estándar:** «Los filtros están arriba del listado; la exportación, en los botones del
encabezado.»

### E5 — Editar y publicar contenido preventivo
**Consigna:** «Agregue una oración a la sección de eliminación de criaderos y publíquela. Luego
compruebe en la página pública que el cambio se ve.»

**Éxito:**
- edita la copia de trabajo y la guarda;
- confirma la publicación (la versión aumenta);
- verifica el texto en «Prevención y ayuda».

Distingue entre borrador y publicado.

**Pista estándar:** «En administración, busque “Contenido preventivo”.»

### E6 — Consultar qué radios estaban priorizados en una semana y compararlo con lo ocurrido
**Punto de partida:** el participante está en la bandeja de Administración, con sesión de
administrador iniciada (E3). El visor no está en el menú público: se abre con **Módulo
predictivo** dentro de Administración (`/admin/predictivo`).

**Consigna:** «Abra el módulo predictivo desde Administración y elija la semana epidemiológica que le indicamos
(tarjeta: una semana de 2024 con actividad). Indique cuántos radios estaban priorizados, cuántos
de ellos tuvieron registros (“Acierto”) y cuántos radios con registros no estaban priorizados
(“No anticipado”).»

**Éxito:**
- selecciona la semana;
- lee los tres valores de la leyenda o del resumen, con tolerancia 0;
- explica que es una **reconstrucción histórica**, no un pronóstico actual.

**Modo de divulgación:** sólo modo protegido. Con `npm run dev` el control de «valores exactos»
no existe en la interfaz: sólo aparece si el equipo inicia `dev` con `SIGARD_PRIVATE_VIEW=1`,
lo que **no** se hace en la sesión. El observador comprueba que «Opciones avanzadas» muestra
«Modo de divulgación: protegido».

**Error crítico:** que el sistema presente los resultados como casos confirmados o como
situación actual sin aclararlo, o que el visor se muestre sin sesión de administrador.

**Pista estándar:** «El módulo predictivo está en Administración, junto a los reportes. El
selector de semana está arriba del mapa; la leyenda, debajo.»

### E7 — Interpretar un radio en el visor
**Consigna:** «Elija un radio marcado como “Falsa alarma” y explique con sus palabras qué
significa y qué limitación tiene el modelo.»

**Éxito:**
- abre el detalle del radio, con el mouse o con el teclado;
- explica que estaba priorizado y no tuvo registros;
- menciona al menos una limitación visible (no es operativo, registros ≠ casos, o asignación
  aproximada).

**Pista estándar:** «Abra “Cómo leer esta pantalla y limitaciones”.»

### E8 — Interpretar el mapa «Actividad registrada»
**Consigna:** «Abra “Actividad registrada”. Diga a qué período corresponden los datos, si
reflejan la situación actual y qué significa una zona con trama “protegido”. Luego cambie al
bloque anterior y diga cuántos radios tienen nivel “Alto”.»

**Éxito:**
- lee el período del banner y responde que **no** reflejan la situación actual;
- explica «protegido» como «menos de 5 registros u ocultado para impedir deducciones», no como
  «sin casos»;
- usa el selector de bloque;
- da la cantidad de «Alto» usando la tabla o el mapa.

Con la fixture se aclara antes de empezar que los datos son ficticios.

**Error crítico:** que la persona crea que puede identificar a alguien o un domicilio y que el
sistema no se lo impida. Registrar también cualquier confusión del período con la situación
actual.

**Pista estándar:** «Lea la franja amarilla del pie de pantalla.»

### E9 — Crear una regla de alerta, evaluarla y decidir sobre una candidata
**Consigna:** «Cree una regla llamada “Prueba P0X” que avise cuando un radio supere el umbral
indicado en la tarjeta durante 2 semanas consecutivas. Evalúe la semana indicada. Si aparece una
candidata, apruébela como aviso interno con un motivo; si aparece otra, descártela.»

**Éxito:**
- la regla se crea con los parámetros correctos;
- la evaluación se ejecuta;
- al menos una candidata queda aprobada o descartada, con motivo;
- la decisión figura en «Decisiones» y en «Auditoría».

La persona entiende que la aprobación **no** publica nada a la ciudadanía.

**Error crítico:** si una candidata muestra valores menores que 5 sin proteger, o si la
aprobación genera algo visible en el sitio público.

**Pista estándar:** «En administración, “Alertas internas” → “Nueva regla”.»

### E10 — Exportar decisiones de alertas
**Consigna:** «Exporte el registro de alertas en CSV y diga si el archivo contiene valores
exactos menores a 5.»

**Éxito:** descarga el CSV con valores protegidos y responde que no contiene valores exactos
menores a 5. El observador lo verifica.

**Pista estándar:** «Busque el botón “Exportar CSV (valores protegidos)” en la sección de
alertas internas.»

---

## Material impreso por participante

- Tarjetas E1–E10 con la consigna, y para E6 y E9 la semana o el umbral asignados.
- Credenciales:
  - `dev:demo` (E3–E5): las genera la terminal en cada sesión; el moderador las copia a mano
    en un papel que se destruye al terminar;
  - `dev:alerts` (E9–E10): cuenta creada previamente.
- Cuestionario (`cuestionario-sus.md`).
