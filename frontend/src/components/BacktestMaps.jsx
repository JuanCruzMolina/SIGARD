import { useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, GeoJSON, MapContainer, useMap, ZoomControl } from 'react-leaflet'
import L from 'leaflet'
import { binFor, cellCategory, formatPlain, legendItems, outcomeNames, statusPlain } from '../services/predictiveView.mjs'

// Fill, border and dash differ per category, and a dot marks radios with records:
// the map never relies on color alone.
const STYLES = {
  TP: { fillColor: '#087b75', color: '#082b2e', weight: 3 },
  FP: { fillColor: '#087b75', color: '#8a6515', weight: 3, dashArray: '6 4' },
  FN: { fillColor: '#f7f8f4', color: '#5b2f6b', weight: 3 },
  TN: { fillColor: '#f7f8f4', color: '#9aa9a5', weight: 1 },
  protected: { fillColor: '#efe3c4', color: '#a08a4f', weight: 1 },
  outside: { fillColor: '#d5dad8', color: '#657d76', weight: 1, dashArray: '3 3' },
  nodata: { fillColor: '#e3e7e5', color: '#9aa9a5', weight: 1 },
}
const FOCUSABLE = new Set(['TP', 'FP', 'FN', 'value'])
const COUNT_NAMES = { TP: 'aciertos', FP: 'falsas alarmas', FN: 'no anticipados', TN: 'correctamente sin alerta', value: 'radios con valor',
  protected: 'protegidos por privacidad', outside: 'fuera del universo común', nodata: 'sin dato' }

function createMapLink() {
  const maps = new Map(); let syncing = false
  return { register(side, map, bounds) {
    maps.set(side, map)
    function sync() {
      // A peer's setView fires its own moveend synchronously; maps of momentarily different
      // sizes may never round to the same center, so re-entry is blocked.
      if (syncing) return
      syncing = true
      try { follow() } finally { syncing = false }
    }
    function follow() {
      const center = map.getCenter(), camera = `${center.lat.toFixed(6)}/${center.lng.toFixed(6)}/${map.getZoom()}`
      map.getContainer().dataset.btCamera = camera
      for (const [other, peer] of maps) {
        if (other !== side && (Math.abs(peer.getCenter().lat - center.lat) > 1e-7 || Math.abs(peer.getCenter().lng - center.lng) > 1e-7 || peer.getZoom() !== map.getZoom())) {
          peer.setView(center, map.getZoom(), { animate: false })
        }
        if (other !== side) peer.getContainer().dataset.btCamera = camera
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
  // The radio panel or a viewport change resizes the container; Leaflet must re-measure it.
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer()); return () => observer.disconnect()
  }, [map])
  return null
}

function cellText(row, view, layer) {
  const category = cellCategory(row, view)
  if (!FOCUSABLE.has(category) && category !== 'TN') return statusPlain[row?.availability_status] || 'Sin dato'
  if (view === 'presence') return outcomeNames[category]
  const value = layer === 'observed' ? row.observed.quantity : row.predicted.quantity
  return value === null ? 'Sin dato' : `${formatPlain(value, 1)} registros ${layer === 'observed' ? 'observados' : 'esperados'}`
}

function Swatch({ item }) {
  const style = item.color ? { background: item.color } : { background: STYLES[item.key].fillColor, borderColor: STYLES[item.key].color,
    borderWidth: STYLES[item.key].weight > 1 ? 3 : 1, borderStyle: STYLES[item.key].dashArray ? 'dashed' : 'solid' }
  return <i className="pv-swatch" style={style}>{['TP', 'FN'].includes(item.key) && <b className="pv-dot" />}</i>
}

export default function BacktestMaps({ geometry, panels, view, layer = 'expected', mode, radio, onRadio }) {
  const link = useMemo(() => createMapLink(), [])
  const [reset, setReset] = useState(0)
  const select = useRef(onRadio); useEffect(() => { select.current = onRadio })
  const bounds = useMemo(() => L.geoJSON({ ...geometry, features: geometry.features.filter(f => f.properties.common_mask) }).getBounds(), [geometry])
  const centers = useMemo(() => new Map(geometry.features.map(f => [f.properties.radio_id, L.geoJSON(f).getBounds().getCenter()])), [geometry])
  const single = panels.length === 1
  return <section aria-label="Mapa de radios censales" className="pv-maps">
    <a className="pv-skip" href="#pv-after-map">Saltar el mapa</a>
    <div className={single ? 'pv-map-grid pv-map-single' : 'pv-map-grid'}>{panels.map((panel, index) => {
      const lookup = new Map(panel.result.rows.map(r => [r.radio_id, r]))
      const counts = {}; for (const r of panel.result.rows) { const c = cellCategory(r, view); counts[c] = (counts[c] || 0) + 1 }
      const key = `${panel.result.target_week}/${view}/${layer}/${radio}/${panel.key}/${mode}`
      return <figure key={panel.key} className="pv-map-figure">
        <figcaption><div><strong>{panel.title}</strong><span>{panel.subtitle}</span></div>
          {index === 0 && <button type="button" onClick={() => setReset(n => n + 1)}>Restablecer encuadre</button>}</figcaption>
        <MapContainer center={[-29.41, -66.85]} zoom={12} zoomControl={false} zoomAnimation={false} attributionControl={false} scrollWheelZoom={false}
          className="bt-map pv-map" aria-label={`${panel.title}. Usá Tab para recorrer los radios con datos y Enter para ver su detalle.`}>
          <ZoomControl position="topright" /><MapSync link={link} side={panel.key} bounds={bounds} reset={reset} />
          <GeoJSON key={key} data={geometry} style={feature => {
            const id = feature.properties.radio_id; const r = lookup.get(id); const category = cellCategory(r, view)
            let style = STYLES[category] || STYLES.nodata
            if (category === 'value') {
              const value = layer === 'observed' ? r.observed.quantity : r.predicted.quantity
              style = value === null ? STYLES.nodata : { fillColor: binFor(value).color, color: '#40575a', weight: 1 }
            }
            return { ...style, dashArray: style.dashArray || null, fillOpacity: .88, ...(id === radio ? { color: '#c2410c', weight: 5, dashArray: null } : {}) }
          }} onEachFeature={(feature, layerItem) => {
            const id = feature.properties.radio_id; const r = lookup.get(id); const text = `Radio ${id}: ${cellText(r, view, layer)}`
            const label = document.createElement('span'); label.textContent = text
            layerItem.bindTooltip(label); layerItem.on('click', () => select.current(id))
            layerItem.on('add', () => {
              const element = layerItem.getElement()
              if (!element || !FOCUSABLE.has(cellCategory(r, view))) return
              element.setAttribute('tabindex', '0'); element.setAttribute('role', 'button'); element.setAttribute('aria-label', `${text}. Ver detalle.`)
              element.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select.current(id) } })
            })
          }} />
          {view === 'presence' && panel.result.rows.filter(r => r.observed.presence === 1 && ['TP', 'FN'].includes(cellCategory(r, view))).map(r =>
            <CircleMarker key={`${key}/${r.radio_id}`} center={centers.get(r.radio_id)} radius={4} interactive={false}
              pathOptions={{ color: '#ffffff', weight: 1.5, fillColor: '#082b2e', fillOpacity: 1 }} />)}
        </MapContainer>
        <p className="pv-sr">Resumen del mapa: {Object.entries(counts).map(([c, n]) => `${n} ${COUNT_NAMES[c]}`).join(', ')}.</p>
      </figure>
    })}</div>
    <ul className="pv-legend" aria-label="Leyenda del mapa">
      {view === 'presence' && <li><i className="pv-swatch pv-swatch-dot"><b className="pv-dot" /></i>Punto: el radio tuvo registros esa semana</li>}
      {legendItems(view, mode).map(item => <li key={item.key} data-legend={item.key}><Swatch item={item} />{item.label}</li>)}
      {view === 'quantity' && <li className="pv-legend-caption">{layer === 'observed' ? 'Registros observados' : 'Registros esperados'} por radio</li>}
    </ul>
    <span id="pv-after-map" tabIndex="-1" />
  </section>
}
