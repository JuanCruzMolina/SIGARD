import { useCallback, useContext, useEffect, useState } from 'react'
import { alertsRequest, downloadAlertsExport } from '../services/citizenReports'
import { epiWeekOf } from '../services/adminShell.mjs'
import { localResearchEnabled } from '../services/localResearch'
import { Icon } from './AdminLayout'
import { AdminCountersContext } from './adminFrame'
import { Badge, Card, Notice, ScreenHeader, UiButton, UiTable } from './AdminUI'
import {
  ACTION_LABELS, CAPABILITY_LABELS, CHANNEL_NOTE, FLOW_STEPS, MINIMUM_COUNT, PERIODICITY_NOTE, PREVIEW_LABEL, REASON_LABELS,
  RETROSPECTIVE_NOTE, STATUS_LABELS, countText, evaluationText, formatValue, formatWeek, modelName, modelsFor, previewText,
  rulePayload, ruleSummary, validateRuleForm,
} from '../services/internalAlerts.mjs'
import './AdminAlerts.css'

const TABS = [['pending', 'Pendientes'], ['rules', 'Reglas'], ['history', 'Historial'], ['how', 'Cómo funciona']]
const emptyForm = { name: '', capability: 'quantity', model: '', threshold: '5', scope: 'all', radio_text: '', radio_ids: [], consecutive_weeks: 2, enabled: true }

function formFrom(rule) {
  return rule ? {
    name: rule.name, capability: rule.capability, model: rule.model, threshold: rule.threshold ?? '',
    scope: rule.radio_ids ? 'selected' : 'all', radio_text: (rule.radio_ids || []).join(', '), radio_ids: rule.radio_ids || [],
    consecutive_weeks: rule.consecutive_weeks, enabled: rule.enabled,
  } : emptyForm
}

function weekLabel(week) {
  return `SE ${week.target_epi_week}/${week.target_year} · ${formatWeek(week.target_week)}`
}

// F6.2 (docs/diseno/admin-v2/Alertas.dc.html): presentation only; the decision flow, requests,
// validations and texts are the same as before.
const ICONS = {
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  check: 'M5 12l4 4 10-10',
  cross: 'M6 6l12 12M18 6L6 18',
}
const STATUS_STYLE = { pending: ['warn', ICONS.clock], approved_internal: ['ok', ICONS.check], discarded: ['alert', ICONS.cross] }

// The candidate's week and radio in the predictive viewer (local research only, where it exists).
function viewerLink(candidate, models) {
  const week = epiWeekOf(candidate.target_week)
  if (!week) return null
  const reference = models?.find(model => model.id === candidate.rule.model)?.reference
  const params = new URLSearchParams({ anio: String(week.year), se: String(week.week), vista: candidate.rule.capability === 'presence' ? 'donde' : 'cuantos', metodo: reference ? 'referencia' : 'ml' })
  if (/^\d{9}$/.test(candidate.radio_id)) params.set('radio', candidate.radio_id)
  return `/admin/predictivo?${params}`
}

function Evidence({ candidate }) {
  const presence = candidate.rule.capability === 'presence'
  return <UiTable className="alerts-evidence">
    <caption>Evidencia de {countText(candidate.evidence.length, 'semana', 'semanas')} · *observado en la reconstrucción retrospectiva · valores menores a {MINIMUM_COUNT} se muestran como «protegido»</caption>
    <thead><tr><th scope="col">Semana</th><th scope="col">{presence ? `Posición (top-${candidate.rule.k})` : 'Esperados'}</th><th scope="col">Observado*</th><th scope="col">Cumple</th></tr></thead>
    <tbody>{candidate.evidence.map(item => <tr key={item.target_week}>
      <td>{formatWeek(item.target_week)}</td>
      <td>{presence ? `${item.rank} de ${candidate.rule.k}` : formatValue(item.expected)}</td>
      <td data-observed={item.observed ?? ''}>{formatValue(item.observed)}</td>
      <td>{item.met ? 'Sí' : 'No'}</td>
    </tr>)}</tbody>
  </UiTable>
}

function Decision({ candidate, busy, onDecide }) {
  const [mode, setMode] = useState(null)
  const [comment, setComment] = useState('')
  const [reason, setReason] = useState('false_alarm')
  const valid = comment.trim().length >= 3
  if (!mode) return <div className="alerts-actions">
    <button type="button" className="primary-button" disabled={busy} onClick={() => setMode('approve')}>Aprobar como aviso interno</button>
    <button type="button" className="secondary-button" disabled={busy} onClick={() => setMode('discard')}>Descartar</button>
  </div>
  return <form className="alerts-decision" onSubmit={event => { event.preventDefault(); if (valid) onDecide(candidate, mode, comment, reason) }}>
    {mode === 'discard' && <label>Motivo<select value={reason} onChange={event => setReason(event.target.value)}>
      {Object.entries(REASON_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select></label>}
    <label>{mode === 'approve' ? 'Comentario de aprobación (obligatorio)' : 'Detalle del descarte (obligatorio)'}
      <textarea value={comment} maxLength="1000" onChange={event => setComment(event.target.value)} /></label>
    <div className="alerts-actions">
      <button className="primary-button" disabled={busy || !valid}>{mode === 'approve' ? 'Confirmar aprobación' : 'Confirmar descarte'}</button>
      <button type="button" className="text-button" disabled={busy} onClick={() => { setMode(null); setComment('') }}>Cancelar</button>
    </div>
  </form>
}

function CandidateCard({ candidate, busy, onDecide, models }) {
  const [tone, icon] = STATUS_STYLE[candidate.status] || ['neutral', null]
  const week = epiWeekOf(candidate.target_week)
  const link = localResearchEnabled() ? viewerLink(candidate, models) : null
  return <article className="alerts-card ui-card" data-candidate={candidate.id} data-status={candidate.status} aria-labelledby={`alerts-candidate-${candidate.id}`}>
    <header>
      <h3 id={`alerts-candidate-${candidate.id}`}>Radio <span className="mono">{candidate.radio_id}</span> · semana del {formatWeek(candidate.target_week)}</h3>
      <Badge tone={tone} icon={icon} className={`status-chip alert-${candidate.status}`}>{STATUS_LABELS[candidate.status]}</Badge>
    </header>
    <dl className="alerts-facts">
      <div><dt>Regla</dt><dd>{candidate.rule.name}</dd></div>
      <div><dt>Condición</dt><dd>{ruleSummary(candidate.rule, candidate.rule.k)}</dd></div>
      <div><dt>Pregunta y modelo</dt><dd>{CAPABILITY_LABELS[candidate.rule.capability]} · {modelName(candidate.rule.model)}</dd></div>
      {week && <div><dt>Semana epidemiológica</dt><dd className="mono mono-week">SE {week.week}/{week.year}</dd></div>}
    </dl>
    {candidate.rule_changed_since && <Notice tone="warn" icon={null} className="alerts-warning"><p>La regla se editó después de generar esta candidata; se muestra la versión usada en la evaluación.</p></Notice>}
    <Evidence candidate={candidate} />
    {candidate.status === 'pending'
      ? <Decision candidate={candidate} busy={busy} onDecide={onDecide} />
      : <p className="alerts-decided">{candidate.status === 'discarded' ? `Motivo: ${REASON_LABELS[candidate.discard_reason]} · ` : ''}«{candidate.decision_comment}» · {candidate.decided_by} · {new Date(candidate.decided_at).toLocaleString('es-AR')}</p>}
    <div className="alerts-card-foot">
      <p className="alerts-blocked">Publicación ciudadana: bloqueada (fuera del alcance del prototipo).</p>
      {link && <UiButton to={link} className="alerts-map-link">Ver en el mapa</UiButton>}
    </div>
  </article>
}

function RuleForm({ token, status, rule, busy, onSave, onCancel, onFail }) {
  const [form, setForm] = useState(() => formFrom(rule))
  const [errors, setErrors] = useState({})
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const models = modelsFor(status, form.capability)
  // The selected model always belongs to the chosen question (metadata default, else the first).
  const model = models.some(item => item.id === form.model) ? form.model : (models.find(item => item.default) || models[0])?.id || ''
  const ids = form.radio_text.split(/[\s,;]+/).map(value => value.trim().toUpperCase()).filter(Boolean)
  const payload = rulePayload({ ...form, model, radio_ids: ids })
  const key = JSON.stringify(payload)
  const k = models.find(item => item.id === model)?.rule?.k

  function change(event) {
    const { name, value, type, checked } = event.target
    setForm(current => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }

  function check() {
    const found = validateRuleForm({ ...form, model, radio_ids: payload.radio_ids || [] }, status)
    const unknown = (payload.radio_ids || []).filter(id => !status.radio_ids.includes(id))
    if (unknown.length) found.radio_ids = `Radios fuera del territorio común: ${unknown.slice(0, 5).join(', ')}`
    setErrors(found)
    return !Object.keys(found).length
  }

  async function runPreview() {
    if (!check()) return
    setPreviewing(true)
    try { setPreview({ key, value: await alertsRequest(token, '/rules/preview', { method: 'POST', body: key }) }) }
    catch (error) { onFail(error) }
    finally { setPreviewing(false) }
  }

  const current = preview?.key === key ? preview.value : null
  return <form className="alerts-rule-form" onSubmit={event => { event.preventDefault(); if (check() && current) onSave(payload, rule) }} aria-busy={busy || previewing}>
    <h3>{rule ? `Editar «${rule.name}»` : 'Nueva regla'}</h3>
    <label>Nombre<input name="name" value={form.name} maxLength="80" onChange={change} />{errors.name && <span className="field-error">{errors.name}</span>}</label>
    <fieldset className="alerts-inline"><legend>Pregunta</legend>
      <label><input type="radio" name="capability" value="presence" checked={form.capability === 'presence'} onChange={change} /> ¿Dónde? (entre los radios con mayor prioridad)</label>
      <label><input type="radio" name="capability" value="quantity" checked={form.capability === 'quantity'} onChange={change} /> ¿Cuántos? (registros esperados)</label>
    </fieldset>
    <label>Modelo<select name="model" value={model} onChange={change}>
      {models.map(item => <option key={item.id} value={item.id}>{modelName(item.id)}{item.reference ? '' : ' · experimental, no promovido'}</option>)}
    </select>{errors.model && <span className="field-error">{errors.model}</span>}</label>
    {form.capability === 'quantity'
      ? <label>Umbral de registros esperados (mínimo {MINIMUM_COUNT})<input name="threshold" inputMode="decimal" value={form.threshold} onChange={change} />
          <small>Lo elige el administrador. El mínimo protege celdas pequeñas: un valor esperado bajo puede revelar un conteo observado.</small>
          {errors.threshold && <span className="field-error">{errors.threshold}</span>}</label>
      : <p className="alerts-help">Condición fija del modelo: el radio queda entre los {k ?? 10} con mayor prioridad de la semana.</p>}
    <fieldset className="alerts-inline"><legend>Radios</legend>
      <label><input type="radio" name="scope" value="all" checked={form.scope === 'all'} onChange={change} /> Todo el territorio común</label>
      <label><input type="radio" name="scope" value="selected" checked={form.scope === 'selected'} onChange={change} /> Radios elegidos</label>
    </fieldset>
    {form.scope === 'selected' && <label>Códigos de radio (separados por coma)<textarea name="radio_text" value={form.radio_text} onChange={change} />
      {errors.radio_ids && <span className="field-error">{errors.radio_ids}</span>}</label>}
    <label>Semanas consecutivas requeridas<select name="consecutive_weeks" value={form.consecutive_weeks} onChange={change}>
      {[1, 2, 3, 4].map(value => <option key={value} value={value}>{value}</option>)}
    </select><small>Exigir más semanas reduce las falsas alarmas a costa de avisar más tarde.</small></label>
    <label className="alerts-check"><input type="checkbox" name="enabled" checked={form.enabled} onChange={change} /> Regla activa</label>
    <section className="alerts-preview" aria-live="polite">
      <h4>{PREVIEW_LABEL}</h4>
      {current ? <p data-preview-activations={current.activations}>{previewText(current)}</p>
        : <p>Calculá la frecuencia histórica antes de guardar{preview ? ' (la regla cambió desde el último cálculo)' : ''}.</p>}
      <button type="button" className="secondary-button" disabled={busy || previewing} onClick={runPreview}>{previewing ? 'Calculando… (la primera vez puede tardar)' : 'Calcular frecuencia histórica'}</button>
    </section>
    <div className="alerts-actions">
      <button className="primary-button" disabled={busy || !current}>{rule ? 'Guardar cambios' : 'Guardar regla'}</button>
      <button type="button" className="text-button" onClick={onCancel}>Cancelar</button>
    </div>
  </form>
}

export default function AdminAlerts({ token, onSessionExpired }) {
  const [tab, setTab] = useState('pending')
  const [status, setStatus] = useState(null)
  const [rules, setRules] = useState([])
  const [candidates, setCandidates] = useState([])
  const [auditRows, setAuditRows] = useState([])
  const [editing, setEditing] = useState(null)
  const [targetWeek, setTargetWeek] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const refreshCounters = useContext(AdminCountersContext)

  const fail = useCallback(requestError => {
    if (requestError.status === 401 || requestError.status === 403) onSessionExpired('La sesión venció, fue revocada o ya no tiene permisos. Ingresá nuevamente.')
    else setError(requestError.status ? requestError.message : 'No se pudo conectar con la API administrativa. Intentá nuevamente.')
  }, [onSessionExpired])

  const reload = useCallback(() => Promise.all([
    alertsRequest(token, '/status'), alertsRequest(token, '/rules'), alertsRequest(token, '/candidates'), alertsRequest(token, '/audit?limit=50'),
  ]).then(([nextStatus, nextRules, nextCandidates, nextAudit]) => {
    setStatus(nextStatus); setRules(nextRules); setCandidates(nextCandidates); setAuditRows(nextAudit)
    setTargetWeek(current => current || nextStatus.weeks?.at(-1)?.target_week || '')
  }).catch(fail), [fail, token])

  useEffect(() => { reload() }, [reload])

  async function act(operation, message) {
    setBusy(true); setError(''); setNotice('')
    try { const result = await operation(); setNotice(typeof result === 'string' ? result : message); await reload(); refreshCounters() } catch (requestError) { fail(requestError) } finally { setBusy(false) }
  }

  const evaluate = () => act(async () => {
    const result = await alertsRequest(token, '/evaluations', { method: 'POST', body: JSON.stringify({ target_week: targetWeek }) })
    return evaluationText(result.evaluation.summary)
  }, 'Evaluación registrada.')

  const decide = (candidate, mode, comment, reason) => act(() => alertsRequest(token, `/candidates/${candidate.id}/${mode}`, {
    method: 'POST', body: JSON.stringify(mode === 'approve' ? { revision: candidate.revision, comment } : { revision: candidate.revision, reason, comment }),
  }), mode === 'approve' ? 'Candidata aprobada como aviso interno.' : 'Candidata descartada.')

  const saveRule = (payload, rule) => act(async () => {
    await alertsRequest(token, rule ? `/rules/${rule.id}` : '/rules', {
      method: rule ? 'PATCH' : 'POST', body: JSON.stringify(rule ? { ...payload, revision: rule.revision } : payload),
    })
    setEditing(null)
  }, rule ? 'Regla actualizada.' : 'Regla creada.')

  const pending = candidates.filter(candidate => candidate.status === 'pending')
  const decided = candidates.filter(candidate => candidate.status !== 'pending')
  const kFor = rule => status?.models?.find(model => model.id === rule.model)?.rule?.k

  const activeRules = rules.filter(rule => rule.enabled)
  const newRule = () => { setTab('rules'); setEditing('new') }

  return <main className="admin-page admin-alerts">
    <ScreenHeader breadcrumb={[{ label: 'Inicio', to: '/admin/inicio' }, { label: 'Alertas internas' }]} title="Alertas internas"
      subtitle="Rol administrador · avisos sólo en este panel · sin correo, SMS ni publicación ciudadana."
      aside={<UiButton variant="primary" disabled={busy || !status?.source_available} onClick={newRule}>Nueva regla</UiButton>} />
    <section className="alerts-banner ui-card" role="note" aria-label="Cómo funciona una alerta interna">
      <p className="alerts-banner-title"><Icon d={ICONS.shield} size={20}/><strong>Ningún algoritmo publica alertas.</strong></p>
      <ol className="alerts-steps">{FLOW_STEPS.map(([title], index) => <li key={title}><span className="mono">{index + 1}</span> {title}</li>)}</ol>
      <p>{CHANNEL_NOTE}</p>
      <p>{RETROSPECTIVE_NOTE}{status?.fictional ? ' Fuente ficticia generada para pruebas.' : ''}</p>
    </section>
    {status && !status.source_available && <Notice tone="danger" icon={null} role="alert" className="form-error admin-error"><p>{status.reason || 'Fuente de predicciones no disponible: las alertas internas se evalúan sólo en el entorno local de investigación (npm run dev).'}</p></Notice>}
    {error && <Notice tone="danger" icon={null} role="alert" className="form-error admin-error"><p>{error}</p></Notice>}
    {notice && <Notice tone="info" icon={ICONS.check} role="status" className="account-notice"><p>{notice}</p></Notice>}
    <nav className="alerts-tabs" aria-label="Secciones de alertas">{TABS.map(([id, label]) => <button key={id} type="button" data-tab={id} aria-pressed={tab === id} onClick={() => setTab(id)}>
      {label}{id === 'pending' && pending.length ? ` (${pending.length})` : ''}</button>)}</nav>

    {tab === 'pending' && <div className="alerts-layout">
      <section className="alerts-list" aria-label="Candidatas pendientes">
        {pending.length ? pending.map(candidate => <CandidateCard key={candidate.id} candidate={candidate} busy={busy} onDecide={decide} models={status?.models} />)
          : <Card className="alerts-empty-card"><p className="alerts-empty">No hay alertas candidatas pendientes de revisión.</p></Card>}
      </section>
      <aside className="alerts-side" aria-label="Evaluación y reglas activas">
        <Card title="Evaluar una semana" titleId="alerts-evaluate-title" level={2}>
          <form className="alerts-evaluate" onSubmit={event => { event.preventDefault(); if (targetWeek) evaluate() }}>
            <label>Semana a evaluar<select value={targetWeek} disabled={!status?.source_available} onChange={event => setTargetWeek(event.target.value)}>
              {(status?.weeks || []).map(week => <option key={week.target_week} value={week.target_week}>{weekLabel(week)}</option>)}
            </select></label>
            <button className="primary-button" disabled={busy || !status?.source_available || !targetWeek}>Evaluar semana</button>
            <small>{PERIODICITY_NOTE} Las reglas activas generan alertas candidatas; nada se notifica fuera de este panel.</small>
          </form>
        </Card>
        <Card title="Reglas activas" titleId="alerts-active-title" level={2} className="alerts-active">
          {activeRules.length ? <ul>{activeRules.map(rule => <li key={rule.id}><strong>{rule.name}</strong><span>{ruleSummary(rule, kFor(rule))}</span></li>)}</ul>
            : <p className="alerts-empty">No hay reglas activas.</p>}
          <button type="button" className="text-button" onClick={() => setTab('rules')}>Ver todas las reglas</button>
        </Card>
      </aside>
    </div>}

    {tab === 'rules' && <section className="panel" aria-label="Reglas">
      {editing !== null && status?.source_available
        ? <Card className="alerts-form-card"><RuleForm key={editing === 'new' ? 'new' : editing.id} token={token} status={status} rule={editing === 'new' ? null : editing} busy={busy}
            onSave={saveRule} onCancel={() => setEditing(null)} onFail={fail} /></Card>
        : <button type="button" className="primary-button" disabled={!status?.source_available} onClick={() => setEditing('new')}>Nueva regla</button>}
      <ul className="alerts-rules">{rules.map(rule => <li key={rule.id} data-rule={rule.id} className="ui-card">
        <div><strong>{rule.name}</strong> <Badge tone={rule.enabled ? 'ok' : 'neutral'} className={`status-chip ${rule.enabled ? 'alert-active' : 'alert-inactive'}`}>{rule.enabled ? 'Activa' : 'Inactiva'}</Badge></div>
        <p>{ruleSummary(rule, kFor(rule))}</p>
        <small>Versión {rule.revision} · editada por {rule.updated_by} · {new Date(rule.updated_at).toLocaleString('es-AR')}</small>
        <button type="button" className="text-button" disabled={busy || !status?.source_available} onClick={() => setEditing(rule)}>Editar</button>
      </li>)}</ul>
      {!rules.length && <p className="alerts-empty">Todavía no hay reglas.</p>}
    </section>}

    {tab === 'history' && <section className="panel" aria-label="Historial">
      <div className="alerts-actions"><button type="button" className="secondary-button" disabled={busy} onClick={() => downloadAlertsExport(token).catch(fail)}>Exportar CSV (valores protegidos)</button></div>
      <h2>Decisiones</h2>
      {decided.length ? decided.map(candidate => <CandidateCard key={candidate.id} candidate={candidate} busy={busy} onDecide={decide} models={status?.models} />)
        : <p className="alerts-empty">Todavía no hay decisiones registradas.</p>}
      <h2>Auditoría</h2>
      <ol className="prevention-history alerts-audit">{auditRows.map(row => <li key={row.id} data-action={row.action}>
        <span>{ACTION_LABELS[row.action] || row.action}{row.entity_id ? ` · ${row.entity} ${row.entity_id}` : ''}</span>
        <span>{row.actor}</span><time>{new Date(row.created_at).toLocaleString('es-AR')}</time>
        {row.after?.comment && <small>«{row.after.comment}»</small>}
      </li>)}</ol>
    </section>}

    {tab === 'how' && <section className="panel alerts-how" aria-label="Cómo funciona">
      <h2>Flujo de una alerta interna</h2>
      <ol className="alerts-flow">{FLOW_STEPS.map(([title, text]) => <li key={title}><strong>{title}</strong><span>{text}</span></li>)}</ol>
      <dl>
        <div><dt>Canal</dt><dd>Notificaciones internas en este panel. Sin correo, SMS ni publicación ciudadana automática.</dd></div>
        <div><dt>Periodicidad</dt><dd>{PERIODICITY_NOTE}</dd></div>
        <div><dt>Origen del umbral</dt><dd>Lo define el administrador (mínimo {MINIMUM_COUNT} registros esperados), con la frecuencia histórica de activación a la vista antes de guardar.</dd></div>
        <div><dt>Responsable de aprobación</dt><dd>Un administrador autenticado; cada decisión queda en la auditoría con fecha y responsable.</dd></div>
        <div><dt>Falsas alarmas</dt><dd>Semanas consecutivas, revisión humana obligatoria con comentario o motivo y publicación ciudadana bloqueada.</dd></div>
        <div><dt>Privacidad</dt><dd>Los valores esperados y observados menores a {MINIMUM_COUNT} se muestran como «protegido» en todas las vistas y exportaciones.</dd></div>
      </dl>
    </section>}
  </main>
}
