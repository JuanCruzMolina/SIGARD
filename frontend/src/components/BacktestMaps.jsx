import { useEffect, useMemo, useRef, useState } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap, ZoomControl } from 'react-leaflet'
import L from 'leaflet'
import { binFor, cellCategory, formatPlain, legendItems, outcomeNames, statusPlain } from '../services/predictiveView.mjs'

// Street base map: same OpenStreetMap source and attribution as the other maps of the site
// (already allowed by the CSP). The self-contained private viewer is built with it disabled.
const BASEMAP_ENABLED = import.meta.env.VITE_SIGARD_BASEMAP !== 'off'
const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
const MIN_ZOOM = 11, MAX_ZOOM = 17
const OFFLINE_TEXT = 'Mapa de calles no disponible sin conexión'

// Fill, border, dash and hatching differ per category: the map never relies on color alone.
// Radios with records carry a diagonal hatch over the whole polygon (a zone, never a point).
const STYLES = {
  TP: { fillColor: 'url(#pv-hatch-tp)', color: '#082b2e', weight: 3, pattern: true },
  FP: { fillColor: '#087b75', color: '#8a6515', weight: 3, dashArray: '6 4' },
  FN: { fillColor: 'url(#pv-hatch-fn)', color: '#5b2f6b', weight: 3, pattern: true },
  TN: { fillColor: '#f7f8f4', color: '#6b7d79', weight: 1 },
  protected: { fillColor: 'url(#pv-hatch-protected)', color: '#8a6f2c', weight: 1.2, dashArray: '2 3', pattern: true },
  outside: { fillColor: '#d5dad8', color: '#4f6660', weight: 1, dashArray: '6 3' },
  nodata: { fillColor: '#e3e7e5', color: '#6b7d79', weight: 1 },
}
// CSS equivalents of the SVG hatches, for the legend swatches.
const SWATCH_FILLS = {
  TP: 'repeating-linear-gradient(-45deg, #082b2e 0 2px, rgba(8, 123, 117, .5) 2px 6px)',
  FN: 'repeating-linear-gradient(-45deg, #5b2f6b 0 2px, rgba(247, 248, 244, .6) 2px 6px)',
  protected: 'repeating-linear-gradient(45deg, rgba(138, 111, 44, .6) 0 1px, transparent 1px 6px)',
}
const FOCUSABLE = new Set(['TP', 'FP', 'FN', 'value'])
const COUNT_NAMES = { TP: 'aciertos', FP: 'falsas alarmas', FN: 'no anticipados', TN: 'correctamente sin alerta', value: 'radios con valor',
  protected: 'protegidos por privacidad', outside: 'fuera del universo común', nodata: 'sin dato' }

function hatch(id, background, line, width, rotate) {
  return <pattern id={id} patternUnits="userSpaceOnUse" width="7" height="7" patternTransform={`rotate(${rotate})`}>
    {background && <rect width="7" height="7" fill={background[0]} fillOpacity={background[1]} />}
    <line x1="0" y1="0" x2="0" y2="7" stroke={line[0]} strokeOpacity={line[1]} strokeWidth={width} />
  </pattern>
}

function Hatches() {
  return <svg className="pv-hatches" width="0" height="0" aria-hidden="true" focusable="false"><defs>
    {hatch('pv-hatch-tp', ['#087b75', .45], ['#082b2e', .85], 2.2, 45)}
    {hatch('pv-hatch-fn', ['#f7f8f4', .5], ['#5b2f6b', .85], 2.2, 45)}
    {hatch('pv-hatch-protected', null, ['#8a6f2c', .45], 1, -45)}
  </defs></svg>
}

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
  if (item.color) return <i className="pv-swatch" style={{ background: item.color }} />
  const s = STYLES[item.key]
  return <i className="pv-swatch" style={{ background: SWATCH_FILLS[item.key] || s.fillColor, borderColor: s.color,
    borderWidth: s.weight > 2 ? 3 : 1, borderStyle: s.dashArray ? 'dashed' : 'solid' }} />
}

function pathStyle(style, category, showBase) {
  // Semi-transparent fills let streets show through; hatches carry their own opacity.
  const fillOpacity = style.pattern ? 1 : !showBase ? .88 : category === 'value' ? .5 : .4
  return { fillColor: style.fillColor, color: style.color, weight: style.weight, dashArray: style.dashArray || null, opacity: 1, fillOpacity }
}

export default function BacktestMaps({ geometry, panels, view, layer = 'expected', mode, radio, onRadio }) {
  const link = useMemo(() => createMapLink(), [])
  const [reset, setReset] = useState(0)
  const [streets, setStreets] = useState(BASEMAP_ENABLED)
  // 'loading' until a tile arrives or fails; once any tile loads, isolated failures are ignored.
  const [tiles, setTiles] = useState('loading')
  const select = useRef(onRadio); useEffect(() => { select.current = onRadio })
  const bounds = useMemo(() => L.geoJSON({ ...geometry, features: geometry.features.filter(f => f.properties.common_mask) }).getBounds(), [geometry])
  // Panning and tile requests stay within La Rioja Capital and its surroundings.
  const maxBounds = useMemo(() => bounds.pad(0.6), [bounds])
  const tileEvents = useMemo(() => ({ tileload: () => setTiles('online'), tileerror: () => setTiles(t => t === 'online' ? t : 'offline') }), [])
  const showBase = streets && tiles !== 'offline'
  const toggleStreets = event => { setStreets(event.target.checked); setTiles('loading') }
  const single = panels.length === 1
  return <section aria-label="Mapa de radios censales" className="pv-maps">
    <a className="pv-skip" href="#pv-after-map">Saltar el mapa</a>
    <Hatches />
    {BASEMAP_ENABLED && <div className="pv-map-toolbar">
      <label className="pv-basemap-toggle"><input type="checkbox" checked={streets} onChange={toggleStreets} /> Mostrar calles</label>
      <span className="pv-basemap-offline" role="status">{streets && tiles === 'offline' ? OFFLINE_TEXT : ''}</span>
    </div>}
    <div className={single ? 'pv-map-grid pv-map-single' : 'pv-map-grid'}>{panels.map((panel, index) => {
      const lookup = new Map(panel.result.rows.map(r => [r.radio_id, r]))
      const counts = {}; for (const r of panel.result.rows) { const c = cellCategory(r, view); counts[c] = (counts[c] || 0) + 1 }
      const key = `${panel.result.target_week}/${view}/${layer}/${radio}/${panel.key}/${mode}/${showBase}`
      return <figure key={panel.key} className="pv-map-figure">
        <figcaption><div><strong>{panel.title}</strong><span>{panel.subtitle}</span></div>
          {index === 0 && <button type="button" onClick={() => setReset(n => n + 1)}>Restablecer encuadre</button>}</figcaption>
        <MapContainer center={[-29.41, -66.85]} zoom={12} minZoom={MIN_ZOOM} maxZoom={MAX_ZOOM} maxBounds={maxBounds} maxBoundsViscosity={1}
          zoomControl={false} zoomAnimation={false} attributionControl={BASEMAP_ENABLED} scrollWheelZoom={false}
          className={showBase ? 'bt-map pv-map pv-map-streets' : 'bt-map pv-map'} aria-label={`${panel.title}. Usá Tab para recorrer los radios con datos y Enter para ver su detalle.`}>
          <ZoomControl position="topright" /><MapSync link={link} side={panel.key} bounds={bounds} reset={reset} />
          {streets && <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} className="pv-basetiles" bounds={maxBounds}
            minZoom={MIN_ZOOM} maxZoom={MAX_ZOOM} referrerPolicy="no-referrer" eventHandlers={tileEvents} />}
          <GeoJSON key={key} data={geometry} style={feature => {
            const id = feature.properties.radio_id; const r = lookup.get(id); const category = cellCategory(r, view)
            let style = STYLES[category] || STYLES.nodata
            if (category === 'value') {
              const value = layer === 'observed' ? r.observed.quantity : r.predicted.quantity
              style = value === null ? STYLES.nodata : { fillColor: binFor(value).color, color: '#2f4547', weight: 1.2 }
            }
            return { ...pathStyle(style, category, showBase), ...(id === radio ? { color: '#c2410c', weight: 5, dashArray: null } : {}) }
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
        </MapContainer>
        <p className="pv-sr">Resumen del mapa: {Object.entries(counts).map(([c, n]) => `${n} ${COUNT_NAMES[c]}`).join(', ')}.</p>
      </figure>
    })}</div>
    <ul className="pv-legend" aria-label="Leyenda del mapa">
      {view === 'presence' && <li data-legend="records"><i className="pv-swatch pv-swatch-hatch" />Radio con registros esa semana (zona, no ubicación del caso)</li>}
      {legendItems(view, mode).map(item => <li key={item.key} data-legend={item.key}><Swatch item={item} />{item.label}</li>)}
      {view === 'quantity' && <li className="pv-legend-caption">{layer === 'observed' ? 'Registros observados' : 'Registros esperados'} por radio</li>}
    </ul>
    <p className="pv-map-note">Los colores indican radios censales completos; no representan domicilios ni ubicaciones exactas.</p>
    <span id="pv-after-map" tabIndex="-1" />
  </section>
}
