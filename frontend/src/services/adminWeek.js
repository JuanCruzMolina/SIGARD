import { backtestCalendar } from './backtestResults'
import { discardBody } from './readRetry.mjs'
import { epiWeekLabel, rememberFound } from './adminShell.mjs'
import { lastEvaluableWeek } from './predictiveView.mjs'

// «Datos hasta» (never hand-written), shared by the menu's context box and Inicio (F5) so both show
// the same week. Where the predictive viewer exists (local research with an administrator session)
// it is the viewer's last evaluable week, read from the same /calendar the viewer uses (shared
// cache), with the API's own SE/year. Elsewhere there is no viewer: the week of the public weeks
// manifest (/data/available_weeks.json) is used and `source` says so. null when neither answers.
const loadManifestWeek = rememberFound(() => fetch('/data/available_weeks.json', { cache: 'no-store' })
  .then(response => response.ok ? response.json() : (discardBody(response), null))
  .then(manifest => manifest?.default_cutoff_date ? { label: epiWeekLabel(manifest.default_cutoff_date), date: manifest.default_cutoff_date, source: 'manifiesto de semanas publicado' } : null))
function loadViewerWeek() {
  return backtestCalendar().then(catalog => {
    const last = lastEvaluableWeek(catalog.weeks)
    return last ? { label: `SE ${last.target_epi_week}/${last.target_year}`, date: last.target_end, year: last.target_year, week: last.target_epi_week, source: 'última semana evaluable del visor predictivo' } : null
  }).catch(() => null)
}

export function loadDataWeek(viewer) {
  return viewer ? loadViewerWeek() : loadManifestWeek()
}
