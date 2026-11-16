# Criterios de aceptación

El dictamen se decide con dos grupos de criterios:
- **A. Umbrales de la sesión con usuarios.**
- **B. Verificaciones técnicas.** Las hace el equipo antes o durante la sesión; cada una tiene
  un procedimiento verificable y un resultado sí/no.

Corresponden al punto 13 del tutor: seguridad, protección de datos, alertas, contenido
sanitario y exactitud geográfica.

## A. Umbrales de la sesión

| Id | Criterio | Umbral | Cálculo |
|---|---|---|---|
| A1 | Usabilidad (SUS) | Promedio ≥ 68 | `cuestionario-sus.md`, n = participantes |
| A2 | Eficacia | ≥ 80 % de las tareas asignadas completadas **sin ayuda** | completadas / (completadas + con_ayuda + no_completadas), sobre todas las filas |
| A3 | Seguridad y privacidad en uso | **0** errores críticos | Suma de la columna `errores_criticos` |
| A4 | Utilidad percibida | Media U1–U5 ≥ 3,5 | Media de las medias individuales |
| A5 | Eficiencia (informativo) | Mediana de tiempo ≤ tiempo máximo en cada tarea | Por tarea; no bloquea el dictamen salvo que A2 falle |

## B. Verificaciones técnicas

Registrar cada una en el acta con fecha, commit y resultado. «Comando» remite a comandos
existentes del repositorio; no se modifican para la sesión.

### B1. Seguridad

| Id | Verificación | Procedimiento | Aprobado si |
|---|---|---|---|
| S1 | Sin secretos ni datos versionados | `.\backend\.venv\Scripts\python.exe -B tools/check_repository_security.py` y `git status --short --ignored` | `tracked_sensitive_candidates: 0`; datos privados sólo en rutas ignoradas |
| S2 | Rutas administrativas protegidas | `test_admin_accounts.py`, `test_internal_alerts.py` y `test_prevention_content.py` en la regresión backend (`publication_isolated.py --backend-regression`) | 0 fallas; 401/403 sin token o sin permisos |
| S3 | Sesión revocada | `npm run test:accounts:browser` | Tras rotar o desactivar una cuenta, la sesión se cierra |
| S4 | Recursos públicos aprobados | `npm run test:security` | Sólo los recursos públicos aprobados por hash |
| S5 | Credenciales | Observación durante E3 y E9 | Ninguna credencial queda en pantalla, grabación ni papel conservado |

### B2. Protección de datos

| Id | Verificación | Procedimiento | Aprobado si |
|---|---|---|---|
| P1 | Reportes: la ubicación exacta sólo está en el panel protegido | E2/E4 y `npm run test:citizen` | El estado público contiene sólo código, estado, fechas y mensaje |
| P2 | Mínimo 5 en salidas agregadas | Visor en modo «Protegido», alertas y exportación (E6, E9, E10) | Ningún valor exacto entre 1 y 4 visible ni exportado |
| P3 | Mapa «Actividad registrada» | `npm run test:public-activity`, `test_public_activity.py` e informe de riesgo del paquete | 0 revelaciones; ningún conteo exacto por radio; 2022 excluido |
| P4 | Desactivado sin autorización | `GET /api/v1/public/activity` sin archivo de autorización | 404 |
| P5 | Sin datos reales en el sitio público | `npm run test:public-activity` (ausencia en `public` y `dist`) | Aprobado |
| P6 | Datos históricos rotulados | E8 y prueba de navegador del banner | Banner con período visible en todos los bloques; fecha de generación separada |

### B3. Alertas

| Id | Verificación | Procedimiento | Aprobado si |
|---|---|---|---|
| L1 | Aprobación humana obligatoria | E9 + `test_internal_alerts.py` | Ninguna candidata se convierte en aviso sin decisión explícita con motivo |
| L2 | Sin publicación ciudadana | E9 | Aprobar no altera ninguna página pública |
| L3 | Trazabilidad | Pestañas «Decisiones» y «Auditoría» | Cada decisión tiene autor, fecha, motivo y regla |
| L4 | Límite declarado | Textos de la sección | Se indica que es retrospectivo y que los modelos no están promovidos |

### B4. Contenido sanitario

| Id | Verificación | Procedimiento | Aprobado si |
|---|---|---|---|
| C1 | Fuentes citadas | Revisar cada sección publicada | Cada sección tiene fuente (`source_label` y URL https) |
| C2 | Flujo borrador → publicación | E5 + `test_prevention_content.py` | Lo público cambia sólo al publicar; la versión aumenta; hay auditoría |
| C3 | Revisión institucional del texto | Lectura por el área de comunicación/promoción | Sin observaciones bloqueantes de contenido sanitario |
| C4 | Directorio de centros de salud | E1 | Fuentes y vigencia visibles; sin datos de personas |

### B5. Exactitud geográfica

| Id | Verificación | Procedimiento | Aprobado si |
|---|---|---|---|
| G1 | Universo territorial | Visor y mapa | 263 radios oficiales; los 7 fuera del universo común se rotulan como tales |
| G2 | Unidad mínima publicada | Mapa «Actividad registrada» | Sólo radio censal completo y ciudad; nunca puntos ni domicilios |
| G3 | Asignación declarada | Textos de visor y mapa | Se informa que la asignación a radio es mayormente aproximada |
| G4 | Coincidencia visual | Revisión por personal con conocimiento del territorio (2–3 radios conocidos) | Los límites y la ubicación general coinciden con la cartografía oficial |

## Dictamen

| Dictamen | Condición |
|---|---|
| **Aprobado** | A1–A4 cumplidos y **todas** las verificaciones B aprobadas |
| **Aprobado con observaciones** | A3 y todas las verificaciones de seguridad y protección de datos (S, P) aprobadas; como máximo **dos** de A1, A2, A4 o de las verificaciones L, C y G no cumplidas, con plan de corrección y fecha |
| **No aprobado** | Cualquier error crítico (A3 > 0), cualquier S o P no aprobada, o más de dos incumplimientos del resto |

La aprobación certifica la aceptación del **prototipo académico** en las condiciones probadas.
No habilita el uso operativo ni la publicación de datos reales, que requieren la autorización
institucional específica.
