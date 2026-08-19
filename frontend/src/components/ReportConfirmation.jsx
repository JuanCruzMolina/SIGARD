import { ShieldIcon } from './InfoIcons'

export default function ReportConfirmation({ result, onNewReport }) {
  return <div className="report-confirmation" role="status"><ShieldIcon className="confirmation-icon"/><h3>Reporte recibido: guardá tu código de seguimiento</h3><output>{result.tracking_code}</output><p>{result.message}</p><div><a className="primary-button" href={`#seguimiento?codigo=${result.tracking_code}`}>Consultar estado</a><button className="text-button" type="button" onClick={onNewReport}>Crear otro reporte</button></div></div>
}
