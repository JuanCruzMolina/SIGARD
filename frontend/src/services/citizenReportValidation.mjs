// Same operational rectangle as backend/app/reports.py, not a case geography.
export const REPORT_CENTER = [-29.418, -66.856]
export const REPORT_BOUNDS = [[-29.53, -66.98], [-29.34, -66.76]]

export function insideReportArea(position) {
  return Array.isArray(position) && position.length === 2 && position.every(Number.isFinite) &&
    position[0] >= REPORT_BOUNDS[0][0] && position[0] <= REPORT_BOUNDS[1][0] &&
    position[1] >= REPORT_BOUNDS[0][1] && position[1] <= REPORT_BOUNDS[1][1]
}

export const normalizeReportText = value => value.trim().replace(/\s+/g, ' ')

// Short category names of the administrative inbox (Reportes ciudadanos and Inicio).
export const REPORT_CATEGORY_LABELS = { agua_acumulada: 'Agua acumulada', neumaticos_chatarra: 'Neumáticos o chatarra', microbasural: 'Microbasural', criadero_espacio_publico: 'Criadero en espacio público', alta_presencia_mosquitos: 'Alta presencia de mosquitos', evaluacion_control_vectorial: 'Evaluación de control vectorial', otro: 'Otro' }
