// Same operational rectangle as backend/app/reports.py, not a case geography.
export const REPORT_CENTER = [-29.418, -66.856]
export const REPORT_BOUNDS = [[-29.53, -66.98], [-29.34, -66.76]]

export function insideReportArea(position) {
  return Array.isArray(position) && position.length === 2 && position.every(Number.isFinite) &&
    position[0] >= REPORT_BOUNDS[0][0] && position[0] <= REPORT_BOUNDS[1][0] &&
    position[1] >= REPORT_BOUNDS[0][1] && position[1] <= REPORT_BOUNDS[1][1]
}

export const normalizeReportText = value => value.trim().replace(/\s+/g, ' ')
