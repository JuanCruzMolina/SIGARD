# Formulario de registro de observaciones

Lo completa el observador durante la sesión (impreso o en una copia privada:
`data/interim/official/aceptacion/<fecha>/formulario-observaciones.private.md`). **Sin nombres**:
sólo códigos (P01, P02) y cargos. Después se pasa a `planilla-resultados.csv` (copia privada).

## Datos de la sesión

| Campo | Valor |
|---|---|
| Fecha y hora de inicio / fin | |
| Lugar | |
| Commit (`git rev-parse HEAD`) | |
| Entorno | `npm run dev` con `SIGARD_PUBLIC_ACTIVITY=fixture` · `SIGARD_PRIVATE_VIEW` vacío: ☐ sí |
| P01 · cargo / área | |
| P02 · cargo / área | |
| Moderador / observador (rol) | |
| Grabación | ☐ no ☐ sí, con consentimiento de ambos |

Resultado: **C** = completado sin ayuda · **A** = con ayuda (una pista) · **N** = no completado.
Errores: **L** leve · **G** grave · **X** crítico (definiciones en `protocolo.md`).

## Registro por escenario

| Esc. | Maneja | Inicio | Fin | Resultado (C/A/N) | Pistas | Errores L / G / X | Cumple el criterio de aceptación (sí/no) |
|---|---|---|---|---|---|---|---|
| E1 Sitio público | P01 | | | | | / / | |
| E2 Inicio | P02 | | | | | / / | |
| E3 Reportes ciudadanos | P01 | | | | | / / | |
| E4 Contenido preventivo | P02 | | | | | / / | |
| E5 Módulo predictivo | P01 | | | | | / / | |
| E6 Alertas internas | P02 | | | | | / / | |
| E7 Cuentas | P01 | | | | | / / | |
| E8 Auditoría | P02 | | | | | / / | |

## Observaciones por escenario

Para cada escenario anotar lo que pide «Qué observar» en `escenarios.md`, citas textuales
relevantes (entre comillas, sin datos identificatorios) y sugerencias de las referentes.

| Esc. | Dónde dudó o se equivocó | Cita textual | Sugerencia de la referente | Gravedad propuesta (cosmético / menor / mayor / bloqueante) |
|---|---|---|---|---|
| E1 | | | | |
| E2 | | | | |
| E3 | | | | |
| E4 | | | | |
| E5 | | | | |
| E6 | | | | |
| E7 | | | | |
| E8 | | | | |

## Comprobaciones del observador durante la sesión

| Comprobación | Escenario | Sí / No | Nota |
|---|---|---|---|
| El seguimiento público no muestra descripción ni ubicación | E1 | | |
| «Actividad registrada» muestra el banner con el período y el aviso de datos ficticios | E1 | | |
| Las credenciales no quedan visibles ni guardadas en el navegador | E2, E7 | | |
| La ubicación exacta sólo aparece en el panel protegido de reportes | E3 | | |
| Lo público cambia sólo al publicar; la versión sube | E4 | | |
| Visor en «Modo de divulgación: protegido», sin selector de valores exactos | E5 | | |
| Ningún valor entre 1 y 4 visible en el visor ni en las alertas | E5, E6 | | |
| Aprobar una alerta no cambia nada del sitio público | E6 | | |
| La auditoría no muestra contraseñas, mensajes, notas ni ubicaciones | E8 | | |

## Preguntas abiertas al cierre (antes del cuestionario)

1. ¿Qué parte del sistema le resultaría más útil en su trabajo? ¿Por qué?
2. ¿Qué le faltó o qué cambiaría antes de usarlo con su equipo?
3. ¿Algún texto o resultado le pareció confuso o que pudiera malinterpretarse?

| Pregunta | P01 | P02 |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |

## Defectos detectados

| N.º | Escenario | Descripción (pasos para reproducir) | Gravedad | ¿Bloquea la aceptación? |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

## Cierre

- Cuestionarios SUS y de utilidad entregados: P01 ☐ P02 ☐
- Papeles con credenciales destruidos: ☐
- Entorno detenido (Ctrl+C) y almacén renombrado si corresponde: ☐
- Firma del observador (rol): ______________________
