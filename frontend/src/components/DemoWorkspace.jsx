import { useCallback, useEffect, useMemo, useState } from 'react'
import { demoWorkspaceRequest } from '../services/citizenReports'
import { joinCountGeometry } from '../services/predictivePresentation.mjs'
import { TerritorialMap } from './SigardComponents'
import './DemoWorkspace.css'

const number = value => Number.isFinite(value) ? new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 }).format(value) : 'Sin estimación'
const initialRule = { name: 'Regla de demostración', radio_id: 'all', horizon: 1, threshold: 2, enabled: true }

export default function DemoWorkspace({ token, onSessionExpired }) {
  const [catalog, setCatalog] = useState(null)
  const [catalogError, setCatalogError] = useState('')
  const [catalogRevision, setCatalogRevision] = useState(0)
  const [tab, setTab] = useState('analysis')
  const [date, setDate] = useState('2024-04-07')
  const [horizon, setHorizon] = useState('1')
  const [method, setMethod] = useState('persistence')
  const [radio, setRadio] = useState('')
  const [response, setResponse] = useState({ key: '', data: null, error: '' })
  const [refresh, setRefresh] = useState(0)
  const [csv, setCsv] = useState('')
  const [importResult, setImportResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [operationError, setOperationError] = useState('')
  const [rules, setRules] = useState([])
  const [candidates, setCandidates] = useState([])
  const [rule, setRule] = useState(initialRule)
  const [editing, setEditing] = useState('')
  const [audit, setAudit] = useState([])
  const key = JSON.stringify({ date, horizon, method, radio, refresh })
  const result = response.key === key ? response.data : null
  const queryError = response.key === key ? response.error : ''
  const selected = result?.radios.find(row => row.radio_id === radio)
  const collection = useMemo(() => catalog ? joinCountGeometry(catalog.geometry, result) : null, [catalog, result])
  const request = useCallback(async (path, options) => {
    try { return await demoWorkspaceRequest(token, path, options) }
    catch (error) {
      if (error.status === 401 || error.status === 403) onSessionExpired('La sesión venció o no tiene permisos. Ingresá nuevamente.')
      throw error
    }
  }, [token, onSessionExpired])

  useEffect(() => {
    const controller = new AbortController()
    request('/catalog', { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) { setCatalog(value); setCsv(value.fixture_csv) }
    }).catch(error => { if (!controller.signal.aborted) setCatalogError(error.message) })
    return () => controller.abort()
  }, [request, catalogRevision])

  useEffect(() => {
    if (!catalog || !date) return undefined
    const controller = new AbortController()
    const query = new URLSearchParams({ target_date: date, horizon, method, ...(radio ? { radio_id: radio } : {}) })
    request(`/query?${query}`, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setResponse({ key, data, error: '' })
    }).catch(error => { if (!controller.signal.aborted) setResponse({ key, data: null, error: error.message }) })
    return () => controller.abort()
  }, [catalog, date, horizon, key, method, radio, request])

  const loadAlerts = useCallback(async () => {
    const data = await request('/alerts')
    setRules(data.rules); setCandidates(data.candidates)
    const history = await request('/audit')
    setAudit(history.items)
  }, [request])
  useEffect(() => {
    let active = true
    if (tab === 'alerts') Promise.all([request('/alerts'), request('/audit')]).then(([data, history]) => {
      if (active) { setRules(data.rules); setCandidates(data.candidates); setAudit(history.items) }
    }).catch(error => { if (active) setOperationError(error.message) })
    return () => { active = false }
  }, [request, tab])

  async function operate(action) {
    if (busy) return
    setBusy(true); setOperationError('')
    try { await action() } catch (error) { setOperationError(error.message) }
    finally { setBusy(false) }
  }
  function importCsv(event) {
    event.preventDefault()
    setImportResult(null)
    void operate(async () => {
      const data = await request('/ingestion', { method: 'POST', body: JSON.stringify({ marker: 'SIGARD_FICTIONAL_V1', csv_text: csv }) })
      setImportResult(data); setCandidates([]); setRefresh(value => value + 1)
    })
  }
  function saveRule(event) {
    event.preventDefault()
    void operate(async () => {
      await request(`/alerts${editing ? `/${editing}` : ''}`, { method: editing ? 'PATCH' : 'POST', body: JSON.stringify(rule) })
      setEditing(''); setRule(initialRule); await loadAlerts()
    })
  }
  function evaluate() {
    setCandidates([])
    void operate(async () => {
      await request('/alerts/evaluate', { method: 'POST', body: JSON.stringify({ target_date: date, horizon: Number(horizon) }) })
      await loadAlerts()
    })
  }

  if (catalogError) return <div className="error-state" role="alert"><p>{catalogError}</p><button className="secondary-button" onClick={() => { setCatalogError(''); setCatalogRevision(value => value + 1) }}>Reintentar</button></div>
  if (!catalog) return <p role="status">Cargando el espacio ficticio…</p>
  return <section className="demo-workspace">
    <aside className="method-notice"><div><strong>Territorio completamente ficticio · seis radios D01–D06</strong><p>Geometría inventada, sin relación con La Rioja. No se leen datos privados ni se ejecutan modelos. Persistencia es la referencia; la opción V3 sólo representa su contrato con valores ilustrativos. Sin probabilidades validadas ni alertas oficiales.</p></div></aside>
    <nav className="demo-tabs" aria-label="Módulos de administración demo">{[['analysis', 'Consulta territorial'], ['ingestion', 'Ingestión ficticia'], ['alerts', 'Alertas experimentales']].map(([id, label]) => <button key={id} type="button" aria-current={tab === id ? 'page' : undefined} onClick={() => { setTab(id); setOperationError('') }}>{label}</button>)}</nav>
    {tab !== 'ingestion' && <section className="demo-query-controls" aria-label="Consulta histórica demo">
      <label htmlFor="demo-date">Fecha objetivo<input id="demo-date" type="date" required value={date} onChange={event => setDate(event.target.value)} /></label>
      <label htmlFor="demo-horizon">Horizonte<select id="demo-horizon" value={horizon} onChange={event => setHorizon(event.target.value)}>{catalog.horizons.map(h => <option key={h} value={h}>t+{h} semanas</option>)}</select></label>
      <label htmlFor="demo-week">Semanas ficticias disponibles<select id="demo-week" value={result?.status === 'available' ? result.target_week : ''} onChange={event => setDate(event.target.value)}><option value="" disabled>Elegí una semana</option>{catalog.target_weeks.map(week => <option key={week} value={week}>{week}</option>)}</select></label>
    </section>}
    {operationError && <p className="form-error" role="alert">{operationError}</p>}
    {tab === 'analysis' && <>
      <label className="demo-method" htmlFor="demo-method">Método<select id="demo-method" value={method} onChange={event => setMethod(event.target.value)}><option value="persistence">Persistencia t−1 · referencia predeterminada</option><option value="v3_experimental">V3 experimental · contrato ficticio, sin ejecutar ML</option></select></label>
      <div className="demo-query-result" data-query-key={key} data-query-state={result?.status || (queryError ? 'error' : 'loading')} aria-live="polite">
        {!date ? <p>Ingresá una fecha para consultar.</p> : queryError ? <p role="alert">{queryError}</p> : !result ? <p role="status">Consultando…</p> : result.status !== 'available' ? <div role="status"><h2>Datos insuficientes para esta fecha y horizonte</h2><p>No se generan estimaciones de 2026 ni se extrapolan resultados. Elegí una semana del ejemplo.</p></div> : <><h2>Semana objetivo: {result.target_week} a {result.target_end}</h2><p>Origen: {result.origin_week} · corte: {result.information_cutoff} · t+{result.horizon}</p><p><strong>Subtotal ficticio elegible: {number(result.expected_eligible_total)}</strong> · {result.eligible_radios} de {catalog.radios.length} radios con estimación. Total completo no disponible.</p><p>Versión {result.model_version}. Probabilidad de aparición: en evaluación, sin puntajes visibles. Superioridad de ML frente al baseline: pendiente.</p></>}
      </div>
      <TerritorialMap geojson={collection} view="snapshot_counts" collectionKey={key} selectedRadio={radio} onRadioSelect={value => setRadio(value || '')} showData={result?.status === 'available'} statusMessage="Sin resultados disponibles para la selección actual." disclaimer="Ejemplo ficticio de cantidades; no representa riesgo epidemiológico." snapshotDetails={selected && <dl><div><dt>Estimación ficticia</dt><dd className="demo-estimate">{number(selected.expected_count)}</dd></div><div><dt>Disponibilidad</dt><dd>{selected.estimate_status === 'available' ? 'Conteo reciente disponible' : selected.estimate_status === 'available_with_historical_mean_fallback' ? 'Respaldo histórico ficticio; sin conteo reciente' : 'Información insuficiente; no se reemplaza por cero'}</dd></div></dl>} />
    </>}
    {tab === 'ingestion' && <form className="demo-import" onSubmit={importCsv}><h2>Validar y cargar un lote de ejemplo</h2><p>48 claves inventadas, ocho semanas y seis radios. Sólo admite las fechas y códigos del ejemplo. Vacío significa desconocido, no cero. No pegues datos personales ni archivos sanitarios.</p><label htmlFor="demo-csv">Lote ficticio CSV<textarea id="demo-csv" rows="12" maxLength={12000} value={csv} onChange={event => setCsv(event.target.value)} required /></label><div className="demo-actions"><button className="primary-button" disabled={busy}>{busy ? 'Validando…' : 'Validar y cargar fixture'}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => { setCsv(catalog.fixture_csv); setImportResult(null) }}>Restaurar ejemplo</button></div>{importResult && <p role="status" className="demo-import-result">Lote cargado: {importResult.rows} filas, {importResult.known} conocidas y {importResult.unknown} desconocidas. Originales sin modificar; cambios sólo en esta sesión.</p>}</form>}
    {tab === 'alerts' && <div className="demo-alerts"><h2>Reglas de alerta experimental</h2><p>Comparan cantidades ficticias de persistencia con un umbral configurable. La evaluación es manual; las candidatas requieren revisión y nunca envían notificaciones ni se publican como alertas oficiales.</p>
      <form onSubmit={saveRule} className="demo-rule-form"><label>Nombre de la regla<input value={rule.name} minLength="3" maxLength="80" required onChange={event => setRule({ ...rule, name: event.target.value })}/></label><label>Radio de la regla<select value={rule.radio_id} onChange={event => setRule({ ...rule, radio_id: event.target.value })}><option value="all">Todos los radios ficticios</option>{catalog.radios.map(id => <option key={id}>{id}</option>)}</select></label><label>Horizonte de la regla<select value={rule.horizon} onChange={event => setRule({ ...rule, horizon: Number(event.target.value) })}>{catalog.horizons.map(h => <option key={h} value={h}>t+{h}</option>)}</select></label><label>Umbral de registros ficticios<input type="number" min="0" max="100" step="0.1" required value={rule.threshold} onChange={event => setRule({ ...rule, threshold: event.target.value === '' ? '' : Number(event.target.value) })}/></label><label className="demo-check"><input type="checkbox" checked={rule.enabled} onChange={event => setRule({ ...rule, enabled: event.target.checked })}/>Regla habilitada</label><button className="primary-button" disabled={busy}>{editing ? 'Guardar regla' : 'Crear regla'}</button></form>
      {rules.length ? <ul className="demo-rule-list">{rules.map(row => <li key={row.id}><span><strong>{row.name}</strong> · {row.radio_id} · t+{row.horizon} · ≥{row.threshold} · {row.enabled ? 'Habilitada' : 'Deshabilitada'}</span><button className="secondary-button" disabled={busy} onClick={() => { const { id, ...fields } = row; setEditing(id); setRule(fields) }}>Editar</button></li>)}</ul> : <p>No hay reglas. Creá una para evaluar el ejemplo.</p>}
      <button className="primary-button" type="button" disabled={busy || !date || !rules.length} onClick={evaluate}>Evaluar candidatas para la fecha y horizonte</button>
      <div className="demo-candidates" aria-live="polite">{candidates.length ? <ul>{candidates.map(candidate => <li key={candidate.id}><strong>{candidate.rule_name}</strong> · {candidate.radio_id} · {candidate.target_week} · {number(candidate.expected_count)} registros ficticios · <span>{candidate.status === 'reviewed_demo' ? 'Revisada en demo' : 'Candidata experimental'}</span>{candidate.status !== 'reviewed_demo' && <button className="secondary-button" disabled={busy} onClick={() => void operate(async () => { await request('/alerts/review', { method: 'POST', body: JSON.stringify({ candidate_id: candidate.id }) }); await loadAlerts() })}>Marcar revisada (demo)</button>}</li>)}</ul> : <p>Sin candidatas vigentes. Una fecha sin datos no genera alertas.</p>}</div>
      {audit.length > 0 && <details><summary>Auditoría de esta sesión ficticia</summary><ul>{audit.map((item, index) => <li key={`${item.created_at}-${index}`}>{item.action} · {new Date(item.created_at).toLocaleString('es-AR')}</li>)}</ul></details>}
    </div>}
  </section>
}
