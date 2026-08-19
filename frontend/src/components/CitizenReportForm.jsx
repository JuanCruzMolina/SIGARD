import { useMemo, useState } from 'react'
import L from 'leaflet'
import { MapContainer, Marker, Rectangle, TileLayer, useMapEvents } from 'react-leaflet'
import { createCitizenReport, geocodeAddress } from '../services/citizenReports'
import ReportConfirmation from './ReportConfirmation'
import { PinIcon, ShieldIcon } from './InfoIcons'

const center = [-29.418, -66.856]
const bounds = [[-29.53, -66.98], [-29.34, -66.76]]
const categories = [
  ['agua_acumulada', 'Recipientes o agua acumulada'],
  ['neumaticos_chatarra', 'Neumáticos, chatarra u objetos voluminosos'],
  ['microbasural', 'Microbasural'],
  ['criadero_espacio_publico', 'Posible criadero en un espacio público'],
  ['alta_presencia_mosquitos', 'Alta presencia de mosquitos'],
  ['evaluacion_control_vectorial', 'Solicitar evaluación para control vectorial'],
  ['otro', 'Otro problema relacionado'],
]
const reportIcon = L.divIcon({ className: '', html: '<span class="report-marker"></span>', iconSize: [32, 38], iconAnchor: [16, 34] })

function LocationPicker({ position, onChange }) {
  useMapEvents({ click: (event) => onChange([event.latlng.lat, event.latlng.lng]) })
  return position ? <Marker position={position} icon={reportIcon} draggable eventHandlers={{ dragend: (event) => { const point = event.target.getLatLng(); onChange([point.lat, point.lng]) } }} /> : null
}

export default function CitizenReportForm() {
  const [form, setForm] = useState({ category: '', description: '', address_reference: '', neighborhood: '', privacy_accepted: false })
  const [position, setPosition] = useState(null)
  const [addressSearchAccepted, setAddressSearchAccepted] = useState(false)
  const [locationState, setLocationState] = useState('idle')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const idempotencyKey = useMemo(() => crypto.randomUUID(), [result]) // eslint-disable-line react-hooks/exhaustive-deps
  const update = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.type === 'checkbox' ? event.target.checked : event.target.value }))

  function useMyLocation() {
    if (!navigator.geolocation) return setLocationState('unsupported')
    setLocationState('loading')
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => { setPosition([coords.latitude, coords.longitude]); setLocationState('ready') },
      () => setLocationState('denied'),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    )
  }

  async function findAddress() {
    if (!form.address_reference.trim()) return setError('Escribí una dirección o referencia para buscarla.')
    if (!addressSearchAccepted) return setError('Confirmá el uso del geocodificador antes de buscar la dirección.')
    setLocationState('geocoding'); setError('')
    try {
      const match = await geocodeAddress(form.address_reference)
      setPosition([match.latitude, match.longitude])
      setLocationState('ready')
    } catch (searchError) {
      setLocationState('idle'); setError(searchError.message)
    }
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!position) return setError('Marcá la ubicación aproximada del problema en el mapa.')
    setSubmitting(true)
    try {
      const created = await createCitizenReport({
        ...form,
        latitude: position[0], longitude: position[1],
        privacy_notice_version: '2026-08-19',
      }, idempotencyKey)
      setResult(created)
    } catch (requestError) {
      setError(requestError.message)
    } finally { setSubmitting(false) }
  }

  if (result) return <ReportConfirmation result={result} onNewReport={() => { setResult(null); setPosition(null); setAddressSearchAccepted(false); setForm({ category: '', description: '', address_reference: '', neighborhood: '', privacy_accepted: false }) }} />

  return <section id="reportar" className="info-section report-section" aria-labelledby="report-title">
    <div className="info-section-heading"><div><h2 id="report-title">Reportá un problema de forma anónima</h2></div><p>El registro es interno de SIGARD. No reemplaza una denuncia municipal ni garantiza una intervención.</p></div>
    <div className="privacy-promise"><ShieldIcon className="info-icon"/><p><strong>No pedimos nombre, DNI, teléfono, correo ni datos de salud.</strong> Los datos enviados en el reporte son privados, sólo los verá personal administrador y se eliminarán al vencer la retención. La búsqueda opcional de dirección tiene un consentimiento separado.</p></div>
    <form className="report-form" onSubmit={submit}>
      <fieldset><legend>1. ¿Qué problema observaste?</legend><div className="category-options">{categories.map(([value, label]) => <label key={value}><input type="radio" name="category" value={value} checked={form.category === value} onChange={update} required/><span>{label}</span></label>)}</div></fieldset>
      <fieldset><legend>2. Contanos brevemente</legend><label className="field-label">Descripción del problema<textarea name="description" value={form.description} onChange={update} minLength="20" maxLength="600" required placeholder="Describí qué observaste, sin incluir nombres, teléfonos, DNI ni información de salud."/><small>{form.description.length}/600 caracteres</small></label><div className="two-fields"><div className="field-label"><label htmlFor="address-reference">Dirección o referencia (opcional)</label><input id="address-reference" name="address_reference" value={form.address_reference} onChange={update} maxLength="200" placeholder="Ej. esquina, plaza o calle cercana"/><label className="geocoder-consent"><input type="checkbox" checked={addressSearchAccepted} onChange={(event) => setAddressSearchAccepted(event.target.checked)}/><span>Acepto enviar esta referencia a OpenStreetMap mediante SIGARD sólo para ubicarla.</span></label><button className="address-search" type="button" onClick={findAddress} disabled={locationState === 'geocoding' || !addressSearchAccepted}>{locationState === 'geocoding' ? 'Buscando…' : 'Buscar en el mapa'}</button><small>La consulta se hace desde el servidor de SIGARD: OpenStreetMap no recibe la IP de tu navegador junto con la referencia. También podés marcar el punto sin escribir una dirección.</small></div><label className="field-label">Barrio (opcional)<input name="neighborhood" value={form.neighborhood} onChange={update} maxLength="100"/></label></div></fieldset>
      <fieldset><legend>3. Marcá la ubicación aproximada</legend><div className="location-help"><p>Podés hacer clic en el mapa, mover el marcador o autorizar al navegador una sola vez.</p><button className="secondary-button" type="button" onClick={useMyLocation} disabled={locationState === 'loading'}><PinIcon className="button-icon"/>{locationState === 'loading' ? 'Buscando ubicación…' : 'Usar mi ubicación'}</button></div>{locationState === 'denied' && <p className="field-message">No se obtuvo permiso. Podés marcar el punto manualmente.</p>}{locationState === 'unsupported' && <p className="field-message">Tu navegador no ofrece geolocalización. Usá el mapa manualmente.</p>}<div className="report-map-wrap"><MapContainer center={center} zoom={12} scrollWheelZoom={false} className="report-map"><TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/><Rectangle bounds={bounds} pathOptions={{ color: '#087b75', weight: 2, fillOpacity: .04 }}/><LocationPicker position={position} onChange={setPosition}/></MapContainer></div><p className="coordinate-readout" aria-live="polite">{position ? `Punto seleccionado: ${position[0].toFixed(5)}, ${position[1].toFixed(5)}` : 'Todavía no seleccionaste un punto.'}</p></fieldset>
      <label className="privacy-check"><input type="checkbox" name="privacy_accepted" checked={form.privacy_accepted} onChange={update} required/><span>Leí y acepto que la ubicación y la descripción se usarán sólo para revisión operativa interna. Entiendo que no es un canal municipal oficial y que no debo incluir datos personales.</span></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary-button submit-report" type="submit" disabled={submitting}>{submitting ? 'Enviando de forma segura…' : 'Enviar reporte anónimo'}</button>
    </form>
  </section>
}
