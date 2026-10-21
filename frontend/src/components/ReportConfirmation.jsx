import { useEffect, useRef, useState } from 'react'
import { ShieldIcon } from './InfoIcons'

export default function ReportConfirmation({ result, onNewReport }) {
  const [copyMessage, setCopyMessage] = useState('')
  const code = useRef(null)
  const heading = useRef(null)
  useEffect(() => { heading.current?.focus() }, [])
  async function copyCode() {
    try {
      await navigator.clipboard.writeText(result.tracking_code)
      setCopyMessage('Código copiado.')
    } catch {
      code.current.focus()
      const selection = window.getSelection()
      const range = document.createRange()
      range.selectNodeContents(code.current)
      selection.removeAllRanges(); selection.addRange(range)
      setCopyMessage('No pudimos copiar automáticamente. El código está seleccionado para copiarlo manualmente.')
    }
  }
  return <div className="report-confirmation"><ShieldIcon className="confirmation-icon"/><h3 tabIndex={-1} ref={heading}>Reporte recibido: guardá tu código de seguimiento</h3><output ref={code} tabIndex={0} aria-label="Código de seguimiento">{result.tracking_code}</output><p>{result.message}</p><div><button className="secondary-button" type="button" onClick={copyCode}>Copiar código</button><a className="primary-button" href={`#seguimiento?codigo=${result.tracking_code}`}>Consultar estado</a><button className="text-button" type="button" onClick={onNewReport}>Crear otro reporte</button></div><p role="status">{copyMessage}</p></div>
}
