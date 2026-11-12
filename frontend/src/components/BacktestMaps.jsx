import { useEffect, useMemo, useState } from 'react'
import { GeoJSON, MapContainer, useMap, ZoomControl } from 'react-leaflet'
import L from 'leaflet'
import { confusionNames, formatValue } from '../services/backtestContract.mjs'

const colors = ['#f2f5f0', '#c2dfd4', '#88bca9', '#459781', '#176d60', '#123a3d']
const outlines = { TP: '#087b75', FP: '#926716', FN: '#703f81', TN: '#839591' }
const bins = value => value === null ? '#d5dad8' : colors[value === 0 ? 0 : value <= 1 ? 1 : value <= 2 ? 2 : value <= 5 ? 3 : value <= 10 ? 4 : 5]

function createMapLink() {
  const maps = new Map()
  return { register(side, map, bounds) {
    maps.set(side, map)
    function sync() {
      const center = map.getCenter()
      map.getContainer().dataset.btCamera = `${center.lat.toFixed(6)}/${center.lng.toFixed(6)}/${map.getZoom()}`
      const peer = maps.get(side === 'predicted' ? 'observed' : 'predicted')
      if (peer && (Math.abs(peer.getCenter().lat - center.lat) > 1e-7 || Math.abs(peer.getCenter().lng - center.lng) > 1e-7 || peer.getZoom() !== map.getZoom())) {
        peer.setView(center, map.getZoom(), { animate: false })
      }
    }
    map.on('moveend', sync)
    map.fitBounds(bounds, { padding: [14, 14], animate: false }); sync()
    return () => { map.off('moveend', sync); maps.delete(side) }
  } }
}

function MapSync({ link, side, bounds, reset }) {
  const map = useMap()
  useEffect(() => link.register(side, map, bounds), [map, link, side, bounds, reset])
  return null
}

export default function BacktestMaps({ geometry, result, view, radio, onRadio, source = 'reference' }) {
  const link = useMemo(() => createMapLink(), [])
  const [reset, setReset] = useState(0)
  const bounds = useMemo(() => L.geoJSON({ ...geometry, features: geometry.features.filter(f => f.properties.common_mask) }).getBounds(), [geometry])
  const lookup = useMemo(() => new Map(result.rows.map(r => [r.radio_id, r])), [result])
  const key = `${result.target_week}/${view}/${radio || ''}/${source}/${result.disclosure?.mode}`
  return <section aria-label="Mapas comparables" className="bt-maps-section">
    <div className="bt-section-heading"><h3>Comparación territorial</h3><button type="button" onClick={() => setReset(n => n + 1)}>Restablecer encuadre</button></div>
    <p>Ambos mapas comparten límites, escala y navegación. Seleccioná un radio en cualquiera de ellos o en el selector.</p>
    <div className="bt-dual-maps">{['predicted', 'observed'].map(side => <figure key={side}>
      <figcaption><strong>{side === 'predicted' ? `A · ${source === 'ml' ? 'ML experimental' : 'Referencia estadística'}` : 'B · Registros territoriales asignados'}</strong><span>{view === 'presence' ? 'Presencia de al menos un registro' : 'Cantidad de registros'} · SE {result.target_epi_week}/{result.target_year}</span></figcaption>
      <MapContainer center={[-29.41, -66.85]} zoom={12} zoomControl={false} zoomAnimation={false} attributionControl={false} scrollWheelZoom={false} className="bt-map" aria-label={side === 'predicted' ? 'Mapa de predicción retrospectiva' : 'Mapa de registros asignados'}>
        <ZoomControl position="topright" /><MapSync link={link} side={side} bounds={bounds} reset={reset} />
        <GeoJSON key={key} data={geometry} style={feature => {
          const r = lookup.get(feature.properties.radio_id); const value = r?.[side]?.[view]
          return { fillColor: r?.availability_status === 'privacy_suppressed' ? '#efe3c4' : view === 'quantity' ? bins(value ?? null) : value === null || value === undefined ? '#d5dad8' : value ? '#087b75' : '#f2f5f0',
            fillOpacity: .85, color: feature.properties.radio_id === radio ? '#162d39' : view === 'presence' ? outlines[r?.confusion] || '#839591' : '#657d76',
            weight: feature.properties.radio_id === radio ? 4 : r?.confusion === 'FN' && view === 'presence' ? 2.5 : 1,
            dashArray: r?.availability_status === 'outside_common_territory' ? '3 3' : view === 'presence' && r?.confusion === 'FP' ? '5 3' : null }
        }} onEachFeature={(feature, layer) => {
          const id = feature.properties.radio_id; const r = lookup.get(id); const label = document.createElement('span')
          label.textContent = `Radio ${id} · ${side === 'predicted' ? 'Estimado' : 'Registrado'}: ${formatValue(r?.[side]?.[view])}${r?.confusion ? ` · ${confusionNames[r.confusion]}` : ''}`
          layer.bindTooltip(label);layer.on('click', () => onRadio(id))
        }} />
      </MapContainer>
      <p className="bt-caption">{side === 'observed' ? 'Asignaciones clínicas que pueden ser aproximadas; no son ubicaciones individuales.' : source === 'ml' ? 'Predicción ML guardada y verificada. Sin calibración sanitaria ni uso operativo.' : 'Referencia estadística seleccionada en la etapa 2. Sin uso operativo.'}</p>
    </figure>)}</div>
    <div className="bt-legend" aria-label="Leyenda común">{view === 'presence' ? <>
      <span><i style={{ background: '#087b75' }} />Presencia (1)</span><span><i style={{ background: '#f2f5f0' }} />Sin presencia (0)</span>
      {Object.entries(confusionNames).map(([code, label]) => <span key={code}><i className="bt-outline" style={{ borderColor: outlines[code], borderStyle: code === 'FP' ? 'dashed' : 'solid' }} />{code} · {label}</span>)}
    </> : ['0', '(0, 1]', '(1, 2]', '(2, 5]', '(5, 10]', '> 10'].map((label, i) => <span key={label}><i style={{ background: colors[i] }} />{label} registros</span>)}<span><i style={{ background: '#d5dad8' }} />No disponible</span><span><i style={{ background: '#efe3c4' }} />Protegido por privacidad</span><span><i style={{ background: '#d5dad8', borderStyle: 'dashed' }} />Fuera del conjunto común</span></div>
    <p className="bt-caption">Siete radios quedan fuera de la máscara común. Sus conteos desconocidos para esta comparación no se rellenan con cero. Los contornos TP/FP/FN/TN comparan la decisión de presencia y los registros.</p>
  </section>
}
