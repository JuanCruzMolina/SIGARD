import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { backtestHistory, backtestSetup, backtestWeek, clearBacktestCache, prefetchWeek } from '../services/backtestResults'
import { experimentalView, formatValue } from '../services/backtestContract.mjs'
import { dateLabel, latestEvaluableYear, methodSources, mostActiveWeek, PRIVATE_WARNING, readUrlState, writeUrlState } from '../services/predictiveView.mjs'
import WeekTimeline from './WeekTimeline'
import SummaryCards, { InfoTip } from './SummaryCards'
import BacktestMaps from './BacktestMaps'
import BacktestHistory from './BacktestHistory'
import RadioPanel from './RadioPanel'
import ModelPerformance from './ModelPerformance'
import DataTable from './DataTable'
import './HistoricalBacktest.css'

function Segmented({ label, options, value, onChange, name }) {
  return <div className="pv-segmented" role="group" aria-label={label} data-control={name}>
    {options.map(o => <button key={o.value} type="button" aria-pressed={value === o.value} data-value={o.value} onClick={() => onChange(o.value)}>{o.label}</button>)}
  </div>
}

function Guide() {
  return <div className="pv-guide">
    <dl>
      <dt>Radio censal</dt><dd>Una zona pequeña de la ciudad definida por el censo. La comparación usa 256 de los 263 radios de La Rioja Capital; los 7 restantes no tienen datos comparables y se muestran como “fuera del universo común”.</dd>
      <dt>Semana epidemiológica (SE)</dt><dd>De domingo a sábado, según el calendario argentino. Algunos años tienen semana 53.</dd>
      <dt>Qué se predice</dt><dd>Con los datos disponibles hasta el sábado anterior (“Datos usados hasta”), si cada radio tendrá al menos un registro (¿Dónde?) y cuántos registros tendrá (¿Cuántos?) en la semana elegida.</dd>
      <dt>Registros</dt><dd>Son registros elegibles según la política del proyecto, no casos confirmados ni incidencia. En 2022 incluyen sospechosos y probables. La ubicación por radio puede ser aproximada; no se muestran ubicaciones individuales.</dd>
      <dt>Clima</dt><dd>Temperatura, humedad y lluvia provienen de un único punto de referencia para toda la ciudad, no de mediciones por radio. El modelo ML las usa; el método de referencia no.</dd>
      <dt>2024</dt><dd>2024 ya se había observado durante el desarrollo: es una comparación, no una validación externa.</dd>
      <dt>Privacidad</dt><dd>En modo protegido se ocultan los valores muy pequeños (menores de 5, incluido el cero) y los que permitirían deducirlos. Un valor oculto no significa cero. Las sumas sólo incluyen los radios visibles.</dd>
      <dt>Reconstrucción histórica</dt><dd>Se reconstruye con las fechas de los eventos; no se sabe exactamente cuándo llegó cada dato. Ningún modelo está aprobado para uso operativo ni emite alertas sanitarias.</dd>
    </dl>
    <h3>Glosario</h3>
    <dl className="pv-glossary">
      <dt>Acierto</dt><dd>Radio priorizado que tuvo registros.</dd>
      <dt>Falsa alarma</dt><dd>Radio priorizado sin registros (sólo visible en modo privado).</dd>
      <dt>No anticipado</dt><dd>Radio con registros que no estaba priorizado.</dd>
      <dt>Correctamente sin alerta</dt><dd>Radio sin registros ni prioridad (sólo visible en modo privado).</dd>
      <dt>Protegido</dt><dd>Valor oculto por privacidad. Distinto de “sin dato” (no hay predicción) y de “fuera del universo común”. El cero real sólo se ve en modo privado.</dd>
      <dt>Semana con resultado verificable</dt><dd>Semana con predicción guardada y registros para comparar.</dd>
    </dl>
  </div>
}

function Skeleton() {
  return <div className="pv-loading" aria-hidden="true"><div className="pv-cards">{[0, 1, 2, 3].map(i => <div key={i} className="pv-card pv-skeleton" />)}</div><div className="pv-map pv-skeleton" /></div>
}

export default function HistoricalBacktest() {
  const [params, setParams] = useSearchParams()
  const url = useMemo(() => readUrlState(params), [params])
  const [initialUrl] = useState(url)
  const [disclosure, setDisclosure] = useState('presentation')
  const [attempt, setAttempt] = useState(0)
  const [setup, setSetup] = useState(null)
  const [setupError, setSetupError] = useState('')
  const [histories, setHistories] = useState({})
  const [weekState, setWeekState] = useState(null)

  // Calendar, geometry, metadata and (when the URL names it) the week start together.
  useEffect(() => {
    const controller = new AbortController()
    if (initialUrl.year && initialUrl.week) prefetchWeek(initialUrl.year, initialUrl.week, 'presentation')
    backtestSetup(controller.signal).then(value => { setSetup(value); setSetupError('') })
      .catch(error => { if (!controller.signal.aborted) setSetupError(error.message) })
    return () => controller.abort()
  }, [attempt, initialUrl])

  const weeks = setup?.catalog.weeks
  const selected = weeks && url.year && url.week ? weeks.find(w => w.target_year === url.year && w.target_epi_week === url.week) || null : null
  const historyYear = selected?.target_year ?? (weeks ? latestEvaluableYear(weeks) : null)
  const historyFor = year => histories[`${disclosure}/${year}`]
  const yearHistory = historyFor(historyYear)
  const weekKey = selected ? `${selected.target_week}/${disclosure}/${attempt}` : null
  const current = weekState?.key === weekKey ? weekState : null
  const stale = !current && weekState?.value?.disclosure?.mode === disclosure ? weekState : null
  const evaluableYears = useMemo(() => weeks ? [...new Set(weeks.filter(w => w.availability_status === 'available').map(w => w.target_year))].sort((a, b) => b - a) : [], [weeks])

  // Two quick changes (e.g. method then question) may happen before a re-render: each one
  // builds on the last written state, not on the URL of the previous render.
  const latestUrl = useRef(url)
  useEffect(() => { latestUrl.current = url }, [url])
  const update = useCallback(patch => {
    latestUrl.current = { ...latestUrl.current, ...patch }
    setParams(writeUrlState(latestUrl.current), { replace: true })
  }, [setParams])
  const loadYear = useCallback((year, signal) => {
    const list = setup.catalog.weeks.filter(w => w.target_year === year); const key = `${disclosure}/${year}`
    return backtestHistory(setup.catalog, list[0].target_week, list.at(-1).target_week, '', signal, disclosure)
      .then(value => setHistories(h => ({ ...h, [key]: { value } })))
      .catch(error => { if (!signal?.aborted) setHistories(h => ({ ...h, [key]: { error: error.message } })) })
  }, [setup, disclosure])

  // Year history: immediately when it decides the default week; otherwise after the map is painted.
  const weekReady = Boolean(current?.value)
  useEffect(() => {
    if (!setup || !historyYear || yearHistory || (selected && !weekReady)) return
    const controller = new AbortController(); loadYear(historyYear, controller.signal)
    return () => controller.abort()
  }, [setup, historyYear, yearHistory, selected, weekReady, loadYear])

  // Default week: most disclosable radios in the active mode within the latest evaluable year.
  useEffect(() => {
    if (!setup || selected || !yearHistory?.value) return
    const best = mostActiveWeek(yearHistory.value.series)
    const target = weeks.find(w => w.target_week === best) || weeks.find(w => w.target_year === historyYear && w.availability_status === 'available')
    update({ year: target.target_year, week: target.target_epi_week })
  }, [setup, selected, yearHistory, weeks, historyYear, update])

  useEffect(() => {
    if (!setup || !selected) return
    const controller = new AbortController()
    backtestWeek(setup.catalog, selected, controller.signal, disclosure)
      .then(value => setWeekState({ key: weekKey, value }))
      .catch(error => { if (!controller.signal.aborted) setWeekState({ key: weekKey, error: error.message }) })
    return () => controller.abort()
  }, [setup, selected, weekKey, disclosure])

  // Other evaluable years load one at a time in the background, after the first paint.
  useEffect(() => {
    if (!setup || !weekReady || !yearHistory) return
    const next = evaluableYears.find(y => !histories[`${disclosure}/${y}`])
    if (!next) return
    const controller = new AbortController()
    const timer = setTimeout(() => loadYear(next, controller.signal), 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [setup, weekReady, yearHistory, evaluableYears, histories, disclosure, loadYear])

  function retry() { clearBacktestCache(); setHistories({}); setWeekState(null); setSetupError(''); setAttempt(n => n + 1) }

  if (!setup) return <section className="historical-backtest pv" aria-label="Predicción semanal" aria-busy={!setupError}>
    {setupError ? <div role="alert" className="pv-empty"><p>{setupError}</p><button type="button" onClick={retry}>Reintentar</button></div>
      : <><p role="status">Cargando calendario, mapa y semana inicial…</p><Skeleton /></>}
  </section>

  const loadedSeries = Object.entries(histories).filter(([k, h]) => k.startsWith(`${disclosure}/`) && h.value).flatMap(([, h]) => h.value.series)
  const globalBest = mostActiveWeek(loadedSeries)
  const goTo = target => target && update({ year: target.target_year, week: target.target_epi_week })
  const goMostActive = () => goTo(weeks.find(w => w.target_week === globalBest))
  const select = (week, yearChange) => {
    const best = yearChange && historyFor(week.target_year)?.value && mostActiveWeek(historyFor(week.target_year).value.series)
    goTo(best ? weeks.find(w => w.target_week === best) : week)
  }
  const shown = (current || stale)?.value
  const view = url.view
  const sources = methodSources(setup.metadata, view)
  const hasML = sources.some(s => s.source === 'ml')
  const method = hasML ? url.method : 'reference'
  const ordered = method === 'reference' ? [...sources].reverse() : sources
  const [primary, other] = ordered
  const display = shown ? Object.fromEntries(sources.map(s => [s.source, experimentalView(shown, s.source)])) : null
  const panels = display ? (method === 'compare' ? sources : [primary]).map(s => ({ key: s.source, title: s.label,
    subtitle: view === 'presence' ? 'Radios priorizados (relleno) y radios con registros (punto)' : url.layer === 'observed' && method !== 'compare' ? 'Registros observados por radio' : 'Registros esperados por radio',
    result: display[s.source] })) : []
  const tableRows = display ? shown.rows.map((r, i) => ({ radio_id: r.radio_id, base: r, ...Object.fromEntries(sources.map(s => [s.source, display[s.source].rows[i]])) })) : []
  const radioRow = url.radio && display ? Object.fromEntries(sources.map(s => [s.source, display[s.source].rows.find(r => r.radio_id === url.radio)])) : null
  const mlMissing = shown && hasML && method !== 'reference' && shown.availability_status === 'available' && shown.ml?.[view]?.availability_status !== 'available'
  const climate = shown?.climate
  // Weeks with nothing disclosable get one explanation only, not a map of protected cells.
  const hasCells = shown?.availability_status === 'available' && shown.metrics.n_comparable > 0

  return <section className="historical-backtest pv" aria-label="Predicción semanal" data-state={current?.value ? 'ready' : current?.error ? 'error' : 'loading'} data-week={shown?.target_week || ''}>
    <div className="pv-controls">
      {selected ? <WeekTimeline weeks={weeks} selected={selected} series={historyFor(selected.target_year)?.value?.series} onSelect={select}
        onMostActive={goMostActive} mostActive={globalBest} mode={disclosure} /> : <p role="status">Buscando la semana con más actividad…</p>}
      <div className="pv-toggles">
        <Segmented name="view" label="Pregunta" value={view} onChange={v => update({ view: v })} options={[{ value: 'presence', label: '¿Dónde?' }, { value: 'quantity', label: '¿Cuántos?' }]} />
        <Segmented name="method" label="Método" value={method} onChange={v => update({ method: v })} options={hasML
          ? [{ value: 'ml', label: 'Modelo ML' }, { value: 'reference', label: 'Método de referencia' }, { value: 'compare', label: 'Comparar' }]
          : [{ value: 'reference', label: 'Método de referencia' }]} />
        {view === 'quantity' && method !== 'compare' && <Segmented name="layer" label="Capa del mapa" value={url.layer} onChange={v => update({ layer: v })} options={[{ value: 'expected', label: 'Esperados' }, { value: 'observed', label: 'Observados' }]} />}
      </div>
      {selected && <p className="pv-context">
        <span>Datos usados hasta: <strong>{dateLabel(selected.origin_end)}</strong></span>
        {climate?.availability_status === 'available'
          ? <span>Semana previa: {formatValue(climate.temperature_mean, 1)} °C · {formatValue(climate.humidity_mean, 0)} % humedad · {formatValue(climate.precipitation_total, 1)} mm
            <InfoTip label="Sobre el clima">Un único punto de referencia para toda la ciudad, de la semana anterior a la elegida. El modelo ML lo usa; el método de referencia no.</InfoTip></span>
          : shown && <span>Clima de la semana previa no disponible.</span>}
      </p>}
      <details className="pv-advanced"><summary>Opciones avanzadas</summary>
        <div className="pv-advanced-body">
          <label htmlFor="bt-disclosure">Modo de divulgación</label>
          <select id="bt-disclosure" value={disclosure} onChange={e => setDisclosure(e.target.value)}>
            <option value="presentation">Protegido (por defecto)</option><option value="private">Investigación privada · valores exactos</option></select>
          <p className="pv-caption">{disclosure === 'presentation' ? 'Se ocultan valores muy pequeños para proteger la privacidad: menores de 5, incluidos ceros, y los que permitirían deducirlos. Es una salvaguarda del prototipo, no una autorización institucional de publicación.' : 'Consulta exacta restringida al equipo autorizado en este equipo local. No proyectar, publicar ni compartir conteos pequeños. No habilita uso sanitario operativo.'}</p>
          <label htmlFor="pv-radio">Ver un radio</label>
          <select id="pv-radio" value={url.radio} onChange={e => update({ radio: e.target.value })}><option value="">Ninguno</option>
            {setup.geometry.features.map(f => <option key={f.properties.radio_id} value={f.properties.radio_id}>{f.properties.radio_id}{f.properties.common_mask ? '' : ' · fuera del universo común'}</option>)}</select>
          <p className="pv-caption">Versión del dataset: {setup.metadata.dataset_version} · política: {setup.metadata.data_policy_version}</p>
        </div>
      </details>
    </div>
    {disclosure === 'private' && <p className="pv-private-warning" role="alert">{PRIVATE_WARNING}</p>}

    {current?.error ? <div role="alert" className="pv-empty"><p>{current.error}</p><button type="button" onClick={retry}>Reintentar consulta</button></div>
      : !shown ? <><p role="status">Consultando la semana…</p><Skeleton /></>
      : <div className={current ? 'pv-body' : 'pv-body pv-updating'} aria-busy={!current}>
        {mlMissing && hasCells && <p className="pv-notice" role="status">El modelo ML no tiene predicción guardada para esta semana. <button type="button" onClick={() => update({ method: 'reference' })}>Ver método de referencia</button></p>}
        <SummaryCards result={shown} view={view} primary={primary} other={other} mode={disclosure} onMostActive={goMostActive} mostActive={globalBest && globalBest !== shown.target_week} />
        {hasCells && <div className={radioRow ? 'pv-main pv-main-panel' : 'pv-main'}>
          <BacktestMaps geometry={setup.geometry} panels={panels} view={view} layer={method === 'compare' ? 'expected' : url.layer} mode={disclosure} radio={url.radio} onRadio={id => update({ radio: id })} />
          {radioRow?.reference && <RadioPanel radio={url.radio} rows={radioRow} sources={ordered} view={view} mode={disclosure} result={shown} catalog={setup.catalog} selected={selected} onClose={() => update({ radio: '' })} />}
        </div>}
      </div>}

    {selected && (historyFor(selected.target_year)?.value
      ? <BacktestHistory series={historyFor(selected.target_year).value.series} selected={selected} mode={disclosure} hasML={hasML} onSelect={w => goTo(weeks.find(x => x.target_week === w.target_week))} />
      : historyFor(selected.target_year)?.error ? <p role="alert">{historyFor(selected.target_year).error} <button type="button" onClick={retry}>Reintentar</button></p>
      : <p className="pv-caption" role="status">Cargando evolución de la ciudad…</p>)}

    <details className="pv-section" id="pv-performance"><summary>¿Qué tan bien funciona el modelo?</summary>
      <ModelPerformance metadata={setup.metadata} mode={disclosure} view={view} result={shown}
        histories={Object.fromEntries(Object.entries(histories).filter(([k, h]) => k.startsWith(`${disclosure}/`) && h.value).map(([k, h]) => [k.split('/')[1], h.value]))} />
    </details>
    <details className="pv-section"><summary>Ver datos en tabla</summary>
      {shown ? <DataTable rows={tableRows} series={historyFor(selected?.target_year)?.value?.series} view={view} sources={ordered} mode={disclosure} /> : <p role="status">Cargando…</p>}
    </details>
    <details className="pv-section"><summary>Cómo leer esta pantalla y limitaciones</summary><Guide /></details>
  </section>
}
