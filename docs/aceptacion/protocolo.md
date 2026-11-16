# Protocolo de pruebas de aceptación con el Ministerio de Salud

Kit sin datos reales. Los nombres de las personas participantes **no** se registran en el
repositorio: se usan códigos (P01, P02…) y cargos. La correspondencia código ↔ persona queda,
si hace falta, en un archivo privado ignorado por Git
(`data/interim/official/aceptacion/participantes.private.csv`).

## Objetivo

Comprobar, con usuarios del área destinataria, que SIGARD permite completar las tareas
centrales de sus seis módulos con eficacia, eficiencia y satisfacción aceptables. También
verificar que ninguna tarea expone datos personales ni presenta resultados experimentales o
históricos como información actual.

| Módulo | Contenido |
|---|---|
| 1 | Prevención y ayuda |
| 2 | Reporte ciudadano y seguimiento |
| 3 | Mapa público / actividad registrada |
| 4 | Visor predictivo |
| 5 | Alertas internas |
| 6 | Administración: reportes, cuentas y contenido preventivo |

No es una validación epidemiológica ni acredita el uso operativo del sistema.

## Participantes (por rol)

| Rol | Cantidad sugerida | Función en la sesión |
|---|---|---|
| Usuario/a de vigilancia epidemiológica | 2–3 | Visor, alertas, actividad registrada |
| Usuario/a de comunicación / promoción de la salud | 1–2 | Prevención, contenido preventivo |
| Usuario/a de gestión de reportes | 1–2 | Reportes ciudadanos y exportación |
| Responsable institucional (opcional) | 1 | Dictamen y firma del acta |
| Moderador/a (equipo SIGARD) | 1 | Conduce la sesión, no ayuda salvo bloqueo |
| Observador/a (equipo SIGARD) | 1 | Registra tiempos, errores y comentarios |

Cada participante hace las tareas de su perfil. Las tareas comunes (E1, E2 y E8) las hacen todos.

## Duración: 60–75 minutos por participante

| Bloque | Minutos |
|---|---|
| Bienvenida, consentimiento y explicación del método | 5–8 |
| Tareas (ver `escenarios.md`) | 40–50 |
| Cuestionario SUS + utilidad percibida + preguntas abiertas | 10 |
| Cierre y dudas | 5–7 |

## Entorno

- **Equipo local del equipo SIGARD**, sin despliegue público. Los entornos y comandos están en
  `preparacion-sesion.md`.
- **Modo protegido:**
  - en el visor se usa el modo de divulgación «Protegido (por defecto)»;
  - «Actividad registrada» se muestra **con la fixture ficticia**;
  - **sólo** si existe la autorización institucional formal (archivo privado ligado al hash del
    manifiesto) puede mostrarse el paquete real protegido.
- Reportes, cuentas y contenido preventivo se usan en la demo descartable (`dev:demo`), con datos
  inventados.
- Navegador en una ventana privada nueva para cada participante, sin extensiones ni
  autocompletado de contraseñas.
- No se graba la pantalla salvo consentimiento expreso. Si se graba, no deben verse credenciales
  ni la terminal.

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
- El orden de las tareas comunes se mantiene; las de perfil siguen el orden del documento.

## Rol del observador

- No interviene ni gesticula. Sólo registra.
- Toma el tiempo con cronómetro:
  - **inicio** = fin de la lectura de la tarea;
  - **fin** = la persona declara terminar o se cumple el criterio de éxito.
- Clasifica cada error según la tabla siguiente.
- Anota citas textuales relevantes, sin datos identificatorios.
- Completa `planilla-resultados.csv` (una fila por participante y tarea) en una copia privada:
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

## Después de cada participante

Restablecer el entorno según `preparacion-sesion.md` § «Restablecer entre participantes». Ningún
participante debe ver reportes, reglas ni ediciones de otro.
