import { useEffect, useRef, useState } from 'react'
import { getCitizenReportStatus } from '../services/citizenReports'
import { SearchIcon } from './InfoIcons'

const labels = { recibido: 'Recibido', en_revision: 'En revisión', pendiente_de_derivacion: 'Pendiente de derivación', derivado: 'Derivado', resuelto: 'Resuelto', descartado: 'Descartado' }

export default function ReportStatusLookup() {
  const [code, setCode] = useState(() => (new URLSearchParams(window.location.hash.split('?')[1] || '').get('codigo') || '').trim().toUpperCase())
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const request = useRef(null)
  const input = useRef(null)

  function changeCode(value) {
    request.current?.abort()
    setCode(value.trim().toUpperCase()); setResult(null); setError(''); setLoading(false)
  }

  useEffect(() => {
    function syncCodeFromHash() {
      const value = new URLSearchParams(window.location.hash.split('?')[1] || '').get('codigo')
      if (value) {
        changeCode(value)
        input.current?.scrollIntoView({ block: 'center' })
        input.current?.focus({ preventScroll: true })
      }
    }
    if (new URLSearchParams(window.location.hash.split('?')[1] || '').get('codigo')) {
      input.current?.scrollIntoView({ block: 'center' })
      input.current?.focus({ preventScroll: true })
    }
    window.addEventListener('hashchange', syncCodeFromHash)
    return () => { window.removeEventListener('hashchange', syncCodeFromHash); request.current?.abort() }
  }, [])

  async function lookup(event) {
    event.preventDefault()
    request.current?.abort()
    const current = new AbortController()
    request.current = current
    setLoading(true); setError(''); setResult(null)
    try {
      const status = await getCitizenReportStatus(code, { signal: current.signal })
      if (!current.signal.aborted) setResult(status)
    } catch (requestError) {
      if (!current.signal.aborted) setError(requestError.message)
    } finally { if (!current.signal.aborted) setLoading(false) }
  }

  return <section id="seguimiento" className="status-section" aria-labelledby="status-title"><div><h2 id="status-title">Consultá el estado de un reporte</h2><p>La consulta nunca muestra la descripción, dirección ni coordenadas.</p></div><form onSubmit={lookup} aria-busy={loading}><label htmlFor="tracking-code">Código de seguimiento</label><div><input ref={input} id="tracking-code" value={code} onChange={(event) => changeCode(event.target.value)} maxLength={14} autoComplete="off" spellCheck={false} pattern="SGD-RPT-[A-Z0-9]{6}" placeholder="SGD-RPT-XXXXXX" required/><button className="primary-button" disabled={loading}><SearchIcon className="button-icon"/>{loading ? 'Consultando…' : 'Consultar'}</button></div></form>{error && <p className="form-error" role="alert">{error}</p>}{result && <div className="status-result" role="status"><strong>{result.tracking_code}</strong><span>{labels[result.status] || result.status}</span><p>Recibido: {new Date(result.created_at).toLocaleString('es-AR')}</p><p>Actualizado: {new Date(result.updated_at).toLocaleString('es-AR')}</p>{result.public_status_message && <strong>{result.public_status_message}</strong>}</div>}</section>
}
