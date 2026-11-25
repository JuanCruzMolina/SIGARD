import { useCallback, useEffect, useRef, useState } from 'react'
import RestrictedMarkdown, { SectionSource } from './RestrictedMarkdown'
import { Badge, Card, Notice, ScreenHeader, UiButton } from './AdminUI'
import {
  createPreventionSection, getPreventionHistory, listPreventionSections,
  transitionPreventionSection, updatePreventionSection,
} from '../services/citizenReports'
import { SECTION_LIMITS, SECTION_SLUG, validateSection } from '../services/preventionContent.mjs'
import './AdminPrevention.css'

const EDITABLE = ['title', 'body', 'position', 'source_label', 'source_url']
const emptyForm = { slug: '', title: '', body: '', position: 100, source_label: '', source_url: '' }
const actionLabels = { seed_import: 'Carga inicial', create: 'Borrador creado', update: 'Borrador editado', publish: 'Publicada', unpublish: 'Despublicada' }
const fieldLabels = { slug: 'identificador', title: 'título', body: 'contenido', position: 'orden', source_label: 'fuente', source_url: 'enlace de fuente' }

function formFrom(section) {
  return section ? Object.fromEntries(['slug', ...EDITABLE].map(field => [field, section[field] ?? ''])) : emptyForm
}

// F6.4 (docs/diseno/admin-v2/Contenido.dc.html): presentation only. Requests, the draft → publish
// flow, validations, history and texts are the same; the public page is not touched.
const ICONS = {
  pencil: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z',
  check: 'M5 12l4 4 10-10',
  hidden: 'M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.1A9.8 9.8 0 0 1 12 5c5 0 9 7 9 7a16 16 0 0 1-2.2 2.9M6.1 6.1C3.8 7.6 3 12 3 12s4 7 9 7a9.6 9.6 0 0 0 4-1',
  draft: 'M6 3h9l3 3v15H6zM9 9h6M9 13h6M9 17h3',
}
const STATUS_STYLE = { pending: ['alert', ICONS.pencil], published: ['ok', ICONS.check], draft: ['neutral', ICONS.draft], unpublished: ['neutral', ICONS.hidden] }

function StatusBadge({ section }) {
  const status = statusOf(section)
  const [tone, icon] = STATUS_STYLE[status.key === 'draft' && section.version ? 'unpublished' : status.key]
  return <Badge tone={tone} icon={icon} className="content-badge">{status.label}</Badge>
}

function statusOf(section) {
  if (section.status !== 'published') return { key: 'draft', label: section.version ? 'Despublicada · borrador' : 'Borrador' }
  return section.has_pending_changes ? { key: 'pending', label: 'Publicada · cambios sin publicar' } : { key: 'published', label: `Publicada · v${section.version}` }
}

function changedFields(entry) {
  if (!entry.before || !entry.after) return ''
  const fields = Object.keys(fieldLabels).filter(field => entry.before[field] !== entry.after[field])
  return fields.length ? `Cambios: ${fields.map(field => fieldLabels[field]).join(', ')}` : ''
}

export default function AdminPrevention({ token, onSessionExpired }) {
  const [sections, setSections] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [history, setHistory] = useState([])
  const [confirming, setConfirming] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const confirmHeading = useRef(null)
  const selected = sections?.find(section => section.id === selectedId) || null
  const creating = selectedId === 'new'
  const dirty = creating || !selected || EDITABLE.some(field => String(form[field] ?? '') !== String(selected[field] ?? ''))

  const fail = useCallback((requestError) => {
    if (requestError.status === 401 || requestError.status === 403) onSessionExpired('La sesión venció, fue revocada o ya no tiene permisos. Ingresá nuevamente.')
    else setError(requestError.status ? requestError.message : 'No se pudo conectar con la API administrativa. Intentá nuevamente.')
  }, [onSessionExpired])

  const loadHistory = useCallback((id) => {
    setHistory([])
    getPreventionHistory(token, id).then(setHistory).catch(fail)
  }, [fail, token])

  const reload = useCallback((focusId) => {
    return listPreventionSections(token).then(result => {
      setSections(result)
      const next = result.find(section => section.id === focusId) || null
      if (next) { setSelectedId(next.id); setForm(formFrom(next)); loadHistory(next.id) }
      return result
    }).catch(fail)
  }, [fail, loadHistory, token])

  useEffect(() => { reload() }, [reload])
  useEffect(() => { if (confirming) confirmHeading.current?.focus() }, [confirming])

  function select(section) {
    setError(''); setNotice(''); setFieldErrors({}); setConfirming(null)
    if (section === 'new') { setSelectedId('new'); setForm(emptyForm); setHistory([]); return }
    setSelectedId(section.id); setForm(formFrom(section)); loadHistory(section.id)
  }

  function update(event) {
    const { name, value } = event.target
    setForm(current => ({ ...current, [name]: name === 'position' ? value.replace(/\D/g, '') : value }))
  }

  async function save(event) {
    event.preventDefault()
    if (busy) return
    setError(''); setNotice('')
    const errors = validateSection(form)
    if (creating && !SECTION_SLUG.test(form.slug)) errors.slug = 'Usá minúsculas, números y guiones (por ejemplo, cuidados-en-verano).'
    setFieldErrors(errors)
    if (Object.keys(errors).length) { setError('Revisá los campos marcados antes de guardar.'); return }
    const payload = {
      title: form.title, body: form.body, position: Number(form.position || 0),
      source_label: form.source_label || null, source_url: form.source_url || null,
    }
    setBusy(true)
    try {
      const saved = creating
        ? await createPreventionSection(token, { ...payload, slug: form.slug })
        : await updatePreventionSection(token, selected.id, { ...payload, revision: selected.revision })
      await reload(saved.id)
      setNotice('Borrador guardado. Todavía no es visible en la página pública.')
    } catch (requestError) { fail(requestError) }
    finally { setBusy(false) }
  }

  async function confirmTransition() {
    if (busy || !confirming) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await transitionPreventionSection(token, selected.id, confirming, selected.revision)
      await reload(result.id)
      setNotice(confirming === 'publish' ? `Versión ${result.version} publicada en la página pública.` : 'La sección dejó de mostrarse en la página pública.')
      setConfirming(null)
    } catch (requestError) { setConfirming(null); fail(requestError) }
    finally { setBusy(false) }
  }

  const state = selected ? statusOf(selected) : null
  const canPublish = selected && !dirty && selected.has_pending_changes && selected.source_url && selected.source_label
  const publishHint = !selected ? '' : dirty ? 'Guardá el borrador antes de publicar.' : !selected.source_url || !selected.source_label ? 'Indicá fuente y enlace sanitario para poder publicar.' : !selected.has_pending_changes ? 'No hay cambios pendientes de publicación.' : ''

  return <main className="admin-page admin-prevention">
    <ScreenHeader breadcrumb={[{ label: 'Inicio', to: '/admin/inicio' }, { label: 'Contenido preventivo' }]} title="Contenido preventivo"
      subtitle="Edición institucional de la página pública de prevención. Sólo orientación sanitaria general: nunca datos de personas, casos ni direcciones."
      aside={<UiButton variant="primary" disabled={busy} onClick={() => select('new')}>Nueva sección</UiButton>} />
    {error && <Notice tone="danger" icon={null} role="alert" className="form-error admin-error"><p>{error}</p></Notice>}
    {notice && <Notice tone="info" icon={ICONS.check} role="status" className="account-notice"><p>{notice}</p></Notice>}
    <div className="prevention-admin-grid">
      <Card className="prevention-section-list" title="Secciones" titleId="prevention-sections-title" aria-busy={!sections}>
        {!sections ? <p role="status">Cargando secciones…</p> : !sections.length ? <p>No hay secciones. Ejecutá la carga inicial o creá una nueva.</p> : <ul>{sections.map(section => <li key={section.id}>
          <button type="button" disabled={busy} aria-pressed={selectedId === section.id} className={selectedId === section.id ? 'selected' : ''} onClick={() => select(section)}>
            <strong>{section.title}</strong><StatusBadge section={section}/><small>{section.slug} · orden {section.position}</small>
          </button></li>)}</ul>}
      </Card>

      {selectedId ? <div className="prevention-main">
        <Card className="prevention-editor" title={creating ? 'Nueva sección (borrador)' : `Editar: ${selected?.title || ''}`} titleId="prevention-editor-title"
          actions={state && <p className="prevention-state"><StatusBadge section={selected}/>{selected.published_at && <span>Última publicación {new Date(selected.published_at).toLocaleString('es-AR')}{selected.published_by ? ` por ${selected.published_by}` : ''}</span>}</p>}>
          <form className="admin-update prevention-form" onSubmit={save} noValidate>
            <fieldset disabled={busy}>
              <div className="prevention-fields">
                {creating && <label>Identificador<input name="slug" value={form.slug} onChange={update} maxLength="60" placeholder="cuidados-en-verano" aria-invalid={Boolean(fieldErrors.slug)}/>{fieldErrors.slug && <small className="field-error">{fieldErrors.slug}</small>}</label>}
                <div className="prevention-row">
                  <label>Título<input name="title" value={form.title} onChange={update} maxLength={SECTION_LIMITS.title} aria-invalid={Boolean(fieldErrors.title)}/>{fieldErrors.title && <small className="field-error">{fieldErrors.title}</small>}</label>
                  <label className="prevention-position">Orden<input name="position" inputMode="numeric" value={form.position} onChange={update} maxLength="4"/></label>
                </div>
                <label>Contenido<textarea name="body" value={form.body} onChange={update} maxLength={SECTION_LIMITS.body} rows="9" aria-describedby="markdown-help" aria-invalid={Boolean(fieldErrors.body)}/><small id="markdown-help">Texto plano. Formato permitido: párrafos separados por una línea vacía, listas con «- », **negrita** y [enlace](https://…). No se admite HTML. {form.body.length}/{SECTION_LIMITS.body}</small>{fieldErrors.body && <small className="field-error">{fieldErrors.body}</small>}</label>
                <label>Fuente o referencia sanitaria<input name="source_label" value={form.source_label} onChange={update} maxLength={SECTION_LIMITS.source_label} placeholder="Ministerio de Salud de la Nación" aria-invalid={Boolean(fieldErrors.source_label)}/>{fieldErrors.source_label && <small className="field-error">{fieldErrors.source_label}</small>}</label>
                <label>Enlace de la fuente<input name="source_url" type="url" value={form.source_url} onChange={update} maxLength={SECTION_LIMITS.source_url} placeholder="https://" aria-invalid={Boolean(fieldErrors.source_url)}/>{fieldErrors.source_url && <small className="field-error">{fieldErrors.source_url}</small>}</label>
              </div>
              <section className="prevention-preview" aria-label="Vista previa">
                <h3>Vista previa del borrador</h3>
                <article><h4>{form.title || 'Sin título'}</h4><RestrictedMarkdown text={form.body}/><SectionSource section={{ source_label: form.source_label, source_url: /^https:\/\//.test(form.source_url) ? form.source_url : null }}/></article>
              </section>
              <div className="prevention-actions">
                {!creating && <UiButton variant="primary" disabled={busy || !canPublish} onClick={() => setConfirming('publish')}>Publicar</UiButton>}
                <button className={creating ? 'ui-button ui-button-primary' : 'ui-button ui-button-secondary'} type="submit" disabled={busy || !dirty}>{busy && !confirming ? 'Guardando…' : 'Guardar borrador'}</button>
                {!creating && selected?.status === 'published' && <UiButton className="prevention-unpublish" disabled={busy} onClick={() => setConfirming('unpublish')}>Despublicar</UiButton>}
                {publishHint && !creating && <small>{publishHint}</small>}
              </div>
            </fieldset>
          </form>
          {confirming && <div className="prevention-confirm" role="alertdialog" aria-labelledby="prevention-confirm-title">
            <h3 id="prevention-confirm-title" tabIndex="-1" ref={confirmHeading}>{confirming === 'publish' ? `¿Publicar la versión ${selected.version + 1}?` : '¿Despublicar esta sección?'}</h3>
            <p>{confirming === 'publish' ? 'El contenido guardado será visible de inmediato para cualquier visitante de la página de prevención. Verificá que provenga de una fuente sanitaria oficial.' : 'La sección dejará de mostrarse en la página pública. El texto y su historial se conservan.'}</p>
            <div><UiButton variant="primary" disabled={busy} onClick={confirmTransition}>{confirming === 'publish' ? 'Confirmar publicación' : 'Confirmar despublicación'}</UiButton><UiButton disabled={busy} onClick={() => setConfirming(null)}>Cancelar</UiButton></div>
          </div>}
        </Card>
        {!creating && <Card className="prevention-history" title="Historial" titleId="prevention-history-title">
          {!history.length ? <p>Sin movimientos registrados.</p> : <ol>{history.map(entry => <li key={entry.id}><strong>{actionLabels[entry.action] || entry.action}</strong><span>{entry.actor}</span><time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString('es-AR')}</time>{changedFields(entry) && <small>{changedFields(entry)}</small>}{entry.action === 'publish' && entry.after?.version && <small>Versión {entry.after.version}</small>}</li>)}</ol>}
        </Card>}
      </div> : <Card className="prevention-empty" title="Seleccioná una sección" titleId="prevention-empty-title"><p>Los cambios se guardan como borrador y sólo llegan a la página pública al confirmar la publicación.</p></Card>}
    </div>
  </main>
}
