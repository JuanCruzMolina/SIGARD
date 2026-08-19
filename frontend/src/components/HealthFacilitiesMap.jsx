import { useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import { MapContainer, Marker, TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { PhoneIcon, PinIcon, SearchIcon } from './InfoIcons'

const center = [-29.418, -66.856]
const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

function markerIcon(type, selected) {
  return L.divIcon({
    className: '',
    html: `<span class="facility-marker ${type} ${selected ? 'selected' : ''}"><span class="sr-only">${type === 'caps' ? 'CAPS' : 'Hospital'}</span></span>`,
    iconSize: [30, 36], iconAnchor: [15, 32],
  })
}

function FocusMarker({ feature }) {
  const map = useMap()
  useEffect(() => {
    if (feature) map.flyTo([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], 15, { duration: .45 })
  }, [feature, map])
  return null
}

export default function HealthFacilitiesMap({ collection }) {
  const [query, setQuery] = useState('')
  const [type, setType] = useState('all')
  const [neighborhood, setNeighborhood] = useState('all')
  const [selectedId, setSelectedId] = useState(null)
  const features = collection.features
  const neighborhoods = useMemo(() => [...new Set(features.map((item) => item.properties.neighborhood).filter(Boolean))].sort(), [features])
  const filtered = useMemo(() => features.filter((feature) => {
    const properties = feature.properties
    const haystack = normalize(`${properties.name} ${properties.address} ${properties.neighborhood}`)
    return (type === 'all' || properties.type === type) &&
      (neighborhood === 'all' || properties.neighborhood === neighborhood) &&
      (!query || haystack.includes(normalize(query)))
  }), [features, neighborhood, query, type])
  const selected = filtered.find(({ properties }) => properties.id === selectedId) || filtered[0] || null

  return <section id="centros" className="info-section facilities-section" aria-labelledby="facilities-title">
    <div className="info-section-heading"><div><h2 id="facilities-title">CAPS y hospitales de referencia</h2></div><p>24 CAPS públicos y 3 hospitales, en categorías separadas. Confirmá horarios antes de trasladarte.</p></div>
    <div className="facility-controls">
      <label className="search-control"><span>Buscar por nombre o domicilio</span><div><SearchIcon className="field-icon"/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ej. San Vicente" /></div></label>
      <label><span>Tipo</span><select value={type} onChange={(event) => setType(event.target.value)}><option value="all">Todos</option><option value="caps">CAPS públicos</option><option value="hospital">Hospitales</option></select></label>
      <label><span>Barrio o zona</span><select value={neighborhood} onChange={(event) => setNeighborhood(event.target.value)}><option value="all">Todos</option>{neighborhoods.map((item) => <option key={item}>{item}</option>)}</select></label>
    </div>
    <div className="facility-legend" aria-label="Referencias del mapa"><span><i className="legend-caps"/>CAPS</span><span><i className="legend-hospital"/>Hospital</span><small>{filtered.length} establecimientos visibles</small></div>
    <div className="facility-explorer">
      <div className="facility-map-wrap" aria-label="Mapa de establecimientos de salud">
        <MapContainer center={center} zoom={12} scrollWheelZoom={false} className="facility-map">
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {filtered.map((feature) => <Marker
            key={feature.properties.id}
            position={[feature.geometry.coordinates[1], feature.geometry.coordinates[0]]}
            icon={markerIcon(feature.properties.type, feature.properties.id === selected?.properties.id)}
            eventHandlers={{ click: () => setSelectedId(feature.properties.id) }}
            title={feature.properties.name}
          />)}
          <FocusMarker feature={selectedId ? selected : null}/>
        </MapContainer>
      </div>
      <aside className="facility-detail" aria-live="polite">{selected ? <>
        <span className={`type-label ${selected.properties.type}`}>{selected.properties.type === 'caps' ? 'CAPS público' : 'Hospital de referencia'}</span>
        <h3>{selected.properties.name}</h3>
        <p className="facility-address"><PinIcon className="inline-icon"/>{selected.properties.address}</p>
        <dl><div><dt>Barrio o zona</dt><dd>{selected.properties.neighborhood}</dd></div><div><dt>Horario publicado</dt><dd>{selected.properties.published_hours}</dd></div><div><dt>Servicios relevantes</dt><dd>{selected.properties.services}</dd></div><div><dt>Verificación</dt><dd>{selected.properties.verification_status.replaceAll('_', ' ')}</dd></div></dl>
        <div className="facility-actions">{selected.properties.phone_tel && <a className="secondary-button" href={`tel:${selected.properties.phone_tel}`}><PhoneIcon className="button-icon"/>Llamar</a>}<a className="primary-button" target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${selected.geometry.coordinates[1]},${selected.geometry.coordinates[0]}`}><PinIcon className="button-icon"/>Cómo llegar</a></div>
        <p className="source-caption">Fuente: <a href={selected.properties.source_url} target="_blank" rel="noreferrer">{selected.properties.source_name}</a> · revisado {selected.properties.reviewed_at} · coordenada {selected.properties.coordinate_precision.replaceAll('_', ' ')}.</p>
      </> : <p>No hay resultados para los filtros seleccionados.</p>}</aside>
    </div>
    <details className="facility-list"><summary>Ver listado textual completo ({filtered.length})</summary><div>{filtered.map((feature) => <button type="button" key={feature.properties.id} onClick={() => setSelectedId(feature.properties.id)}><strong>{feature.properties.name}</strong><span>{feature.properties.address} · {feature.properties.neighborhood}</span></button>)}</div></details>
    <p className="directory-notice">{collection.notice}</p>
  </section>
}
