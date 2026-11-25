# Protocolo de pruebas de aceptación con el Ministerio de Salud

Kit sin datos reales. Los nombres de las personas participantes **no** se registran en el
repositorio: se usan códigos (P01, P02…) y cargos. La correspondencia código ↔ persona queda,
si hace falta, en un archivo privado ignorado por Git
(`data/interim/official/aceptacion/participantes.private.csv`).

## Objetivo

Comprobar, con **dos referentes del Ministerio de Salud**, que SIGARD v1.0.0 permite completar
las tareas centrales del sitio público y de las siete secciones de Administración con eficacia,
eficiencia y satisfacción aceptables. También verificar que ninguna tarea expone datos
personales ni presenta resultados experimentales o históricos como información actual.

| Escenario | Sección |
|---|---|
| E1 | Sitio público: prevención, reporte, seguimiento y actividad registrada |
| E2 | Administración · Inicio |
| E3 | Administración · Reportes ciudadanos |
| E4 | Administración · Contenido preventivo |
| E5 | Administración · Módulo predictivo |
| E6 | Administración · Alertas internas |
| E7 | Administración · Cuentas |
| E8 | Administración · Auditoría |

No es una validación epidemiológica ni acredita el uso operativo del sistema.

## Participantes

| Rol | Cantidad | Función en la sesión |
|---|---|---|
| Referente del Ministerio (P01, P02) | 2 | Hacen los escenarios por turnos: una maneja, la otra observa y opina al final de cada escenario |
| Moderador/a (equipo SIGARD) | 1 | Lee las consignas, entrega las tarjetas y sólo da la pista estándar ante un bloqueo |
| Observador/a (equipo SIGARD) | 1 | Toma tiempos y completa `formulario-observaciones.md` |
| Responsable institucional (opcional) | 1 | Dictamen y firma del acta |

## Duración: 30–45 minutos (una sola sesión con las dos referentes)

| Bloque | Minutos |
|---|---|
| Bienvenida, consentimiento y explicación del método | 5 |
| Escenarios E1–E8 (ver `escenarios.md`; ≈ 25 esperados, 39 como máximo) | 20–30 |
| Preguntas abiertas, cuestionario SUS y utilidad percibida | 5–7 |
| Cierre y dudas | 2–3 |

Si el tiempo se acorta, se aplica la reducción indicada en `escenarios.md`, sin quitar
escenarios de Administración.

## Entorno

- **Equipo local del equipo SIGARD**, sin despliegue público. Un único entorno: `npm run dev`
  iniciado con la fixture ficticia de «Actividad registrada» (`SIGARD_PUBLIC_ACTIVITY=fixture`).
  Comandos en `preparacion-sesion.md`.
- **Modo protegido:**
  - el visor sólo ofrece «Modo de divulgación: protegido» (`SIGARD_PRIVATE_VIEW` sin definir);
  - «Actividad registrada» se muestra **con la fixture ficticia**; el paquete real sólo con la
    autorización institucional formal (archivo privado ligado al hash del manifiesto);
  - el visor y las alertas leen los agregados locales protegidos (valores menores a 5 ocultos).
- Reportes, contenido, reglas y cuentas creados en la sesión son **inventados** y quedan en el
  almacén privado de la Administración local, que se renombra al terminar (no se borra).
- Navegador en una ventana privada nueva, sin extensiones ni autocompletado de contraseñas.
- No se graba la pantalla salvo consentimiento expreso de ambas. Si se graba, no deben verse
  credenciales ni la terminal.

## Consentimiento

Antes de empezar se lee y se firma (en papel o formulario institucional, fuera del repositorio):

1. La participación es voluntaria; se puede interrumpir sin dar explicaciones.
2. Se evalúa el sistema, no a la persona.
3. Se registran tiempos, errores y respuestas de forma seudonimizada (código P0X y cargo).
4. Los datos usados son ficticios o agregados y protegidos; no se cargan datos de personas.
5. Las respuestas se usan sólo para el informe de aceptación y la tesis, de forma agregada.
6. Grabación de pantalla: sí / no (marcar).

## Método

- **Pensar en voz alta**: se pide a la persona que comente lo que busca y lo que espera.
- El moderador lee cada tarea textualmente (`escenarios.md`) y entrega la tarjeta impresa.
- **Sin ayuda**, salvo bloqueo:
  - si pasan 60 s sin avance o la persona lo pide, se da **una** pista estándar y la tarea se
    registra como «completada con ayuda»;
  - si se supera el tiempo máximo, la tarea se registra como «no completada» y se pasa a la
    siguiente.
- Los escenarios se hacen en el orden E1–E8: varios usan lo creado en los anteriores.

## Rol del observador

- No interviene ni gesticula. Sólo registra.
- Toma el tiempo con cronómetro:
  - **inicio** = fin de la lectura de la tarea;
  - **fin** = la persona declara terminar o se cumple el criterio de éxito.
- Clasifica cada error según la tabla siguiente.
- Anota citas textuales relevantes, sin datos identificatorios.
- Completa `formulario-observaciones.md` durante la sesión y después `planilla-resultados.csv`
  (una fila por escenario, con quién manejó) en una copia privada:
  `data/interim/official/aceptacion/<fecha>/planilla-resultados.private.csv`.

| Tipo de error | Definición | Ejemplo |
|---|---|---|
| Leve | Desvío corregido por la persona sin consecuencia | Abre una sección equivocada y vuelve |
| Grave | Impide completar sin ayuda o produce un resultado equivocado | Exporta sin filtros cuando debía filtrar |
| Crítico (seguridad/privacidad) | Expone datos personales, ubicaciones exactas fuera del panel protegido, credenciales, o presenta datos históricos/experimentales como actuales | Ver `criterios.md` |

## Registro de tiempos y errores

Por cada tarea se registra:
- código de participante, perfil, tarea y entorno;
- hora de inicio y fin, duración en segundos;
- resultado: `completada` / `con_ayuda` / `no_completada`;
- cantidad de errores leves, graves y críticos;
- pistas dadas;
- observaciones.

Al cerrar la sesión se calculan:
- el SUS (`cuestionario-sus.md`);
- la utilidad percibida;
- la aplicación de los umbrales de `criterios.md`.

Con eso se redacta el acta (`acta-modelo.md`).

## Después de la sesión

Restablecer el entorno según `preparacion-sesion.md` § «Después de la sesión». Una sesión
posterior no debe ver los reportes, reglas, ediciones ni cuentas de esta.
