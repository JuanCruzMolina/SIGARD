import { useEffect, useMemo, useRef, useState } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap, ZoomControl } from 'react-leaflet'
import L from 'leaflet'
import { EXCLUDED_YEAR_TEXT, LEVELS, PROTECTED, blockLabel, blockRange, formatDay, levelCounts, periodBanner, periodText } from '../services/publicActivity.mjs'
import './PublicActivity.css'

// Same street base map pattern as the predictive viewer: OpenStreetMap, attenuated, optional.
const BASEMAP_ENABLED = import.meta.env.VITE_SIGARD_BASEMAP !== 'off'
const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
const OFFLINE_TEXT = 'Mapa de calles no disponible sin conexión'
const LEVEL = Object.fromEntries(LEVELS.map(level => [level.key, level]))
const STYLES = {
  alto: { fillColor: LEVEL.alto.color, color: '#062f2c', weight: 1.4 },
  medio: { fillColor: LEVEL.medio.color, color: '#1d5650', weight: 1.2 },
  bajo: { fillColor: LEVEL.bajo.color, color: '#3a6f68', weight: 1 },
  [PROTECTED]: { fillColor: 'url(#pa-hatch-protected)', color: '#7a6326', weight: 1, dashArray: '2 3', pattern: true },
  outside: { fillColor: '#d5dad8', color: '#4f6660', weight: 1, dashArray: '6 3' },
  nodata: { fillColor: '#eceeed', color: '#8a9692', weight: .8 },
}
const SWATCH = {
  [PROTECTED]: 'repeating-linear-gradient(45deg, rgba(122, 99, 38, .75) 0 1.5px, #fbf8ef 1.5px 6px)',
  outside: '#d5dad8',
}
const STATE_TEXT = { outside: 'Fuera del área analizada', nodata: 'Sin dato publicado' }

function stateOf(id, block, outside) {
  if (outside.has(id)) return 'outside'
  return block.radios[id] || 'nodata'
}
function stateLabel(state) { return LEVEL[state] ? `${LEVEL[state].label}${state === PROTECTED ? '' : ` (${LEVEL[state].range})`}` : STATE_TEXT[state] }

function FitBounds({ bounds }) {
  const map = useMap()
  useEffect(() => { map.fitBounds(bounds, { padding: [14, 14], animate: false }) }, [map, bounds])
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer()); return () => observer.disconnect()
  }, [map])
  return null
}

function ActivityMap({ geometry, block, outside, radio, onRadio }) {
  const [streets, setStreets] = useState(BASEMAP_ENABLED)
  const [tiles, setTiles] = useState('loading')
  const select = useRef(onRadio); useEffect(() => { select.current = onRadio })
  const bounds = useMemo(() => L.geoJSON(geometry).getBounds(), [geometry])
  const maxBounds = useMemo(() => bounds.pad(0.6), [bounds])
  const tileEvents = useMemo(() => ({ tileload: () => setTiles('online'), tileerror: () => setTiles(t => t === 'online' ? t : 'offline') }), [])
  const showBase = streets && tiles !== 'offline'
  const ids = useMemo(() => geometry.features.map(f => f.properties.radio_id), [geometry])
  const counts = levelCounts(block, ids)
  return <section className="pa-map-section" aria-labelledby="pa-map-title">
    <h2 id="pa-map-title">Niveles por radio censal · {blockLabel(block)}</h2>
    <svg className="pa-hatches" width="0" height="0" aria-hidden="true" focusable="false"><defs>
      <pattern id="pa-hatch-protected" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">
        <rect width="7" height="7" fill="#fbf8ef" fillOpacity=".75" /><line x1="0" y1="0" x2="0" y2="7" stroke="#7a6326" strokeOpacity=".8" strokeWidth="1.5" />
      </pattern></defs></svg>
    {BASEMAP_ENABLED && <div className="pa-map-toolbar">
      <label className="pa-basemap-toggle"><input type="checkbox" checked={streets} onChange={e => { setStreets(e.target.checked); setTiles('loading') }} /> Mostrar calles</label>
      <span className="pa-basemap-offline" role="status">{streets && tiles === 'offline' ? OFFLINE_TEXT : ''}</span>
    </div>}
    <MapContainer center={bounds.getCenter()} zoom={12} minZoom={10} maxZoom={17} maxBounds={maxBounds} maxBoundsViscosity={1}
      zoomControl={false} zoomAnimation={false} attributionControl={BASEMAP_ENABLED} scrollWheelZoom={false}
      className={showBase ? 'pa-map pa-map-streets' : 'pa-map'} aria-label={`Mapa de niveles por radio censal para ${blockLabel(block)}. Usá el selector de radio debajo del mapa para consultar cada zona con teclado.`}>
      <ZoomControl position="topright" /><FitBounds bounds={bounds} />
      {streets && <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} className="pa-basetiles" bounds={maxBounds}
        minZoom={10} maxZoom={17} referrerPolicy="strict-origin" eventHandlers={tileEvents} />}
      <GeoJSON key={`${block.id}/${radio}/${showBase}`} data={geometry} style={feature => {
        const id = feature.properties.radio_id, state = stateOf(id, block, outside), style = STYLES[state]
        const fillOpacity = style.pattern ? 1 : showBase ? .62 : .9
        return { fillColor: style.fillColor, color: style.color, weight: style.weight, dashArray: style.dashArray || null, opacity: 1, fillOpacity,
          ...(id === radio ? { color: '#c2410c', weight: 4, dashArray: null } : {}) }
      }} onEachFeature={(feature, layer) => {
        const id = feature.properties.radio_id
        const label = document.createElement('span'); label.textContent = `Radio ${id}: ${stateLabel(stateOf(id, block, outside))}`
        layer.bindTooltip(label); layer.on('click', () => select.current(id))
      }} />
    </MapContainer>
    <p className="pa-sr">Resumen del mapa: {LEVELS.map(l => `${counts[l.key]} radios ${l.label.toLowerCase()}`).join(', ')}.</p>
    <ul className="pa-legend" aria-label="Leyenda del mapa">
      {LEVELS.map(level => <li key={level.key} data-legend={level.key}><i className="pa-swatch" style={{ background: SWATCH[level.key] || level.color }} />
        <span><strong>{level.label}</strong>{level.key !== PROTECTED && ` · ${level.range}`}{level.key === PROTECTED && <small>{level.range}</small>}</span></li>)}
      <li data-legend="outside"><i className="pa-swatch pa-swatch-outside" style={{ background: SWATCH.outside }} /><span><strong>Fuera del área analizada</strong></span></li>
    </ul>
  </section>
}

function RadioDetail({ ids, block, outside, radio, onRadio }) {
  const state = radio ? stateOf(radio, block, outside) : null
  return <div className="pa-radio">
    <label htmlFor="pa-radio">Consultar un radio censal</label>
    <select id="pa-radio" value={radio || ''} onChange={e => onRadio(e.target.value || null)}>
      <option value="">Elegí un radio…</option>
      {ids.map(id => <option key={id} value={id}>Radio {id}</option>)}
    </select>
    <p aria-live="polite">{radio ? <><strong>Radio {radio}</strong> · {blockLabel(block)}: {stateLabel(state)}.</> : 'También podés tocar una zona del mapa.'}</p>
  </div>
}

function CitySeries({ activity, block }) {
  const weeks = useMemo(() => activity.blocks.filter(b => b.year === block.year).flatMap(b => b.city_weeks.map(e => ({ ...e, block: b.id }))), [activity, block.year])
  const max = Math.max(5, ...weeks.map(e => e.value || 0))
  const top = Math.ceil(max / 10) * 10
  const W = 960, H = 210, left = 34, bottom = 24, plot = H - bottom - 10, step = (W - left - 6) / Math.max(weeks.length, 1)
  const y = value => H - bottom - value / top * plot
  const selected = weeks.map((e, i) => e.block === block.id ? i : -1).filter(i => i >= 0)
  const [hover, setHover] = useState(null)
  return <section className="pa-series" aria-labelledby="pa-series-title">
    <h2 id="pa-series-title">Registros semanales en la ciudad · {block.year}</h2>
    <p className="pa-series-note">Todos los registros del departamento capital por semana epidemiológica. Las semanas con menos de 5 registros se muestran como «&lt;5».</p>
    <div className="pa-series-frame">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Serie semanal de registros de la ciudad en ${block.year}; el bloque ${blockLabel(block)} aparece resaltado. La tabla siguiente contiene los mismos valores.`}>
        <pattern id="pa-hatch-series" patternUnits="userSpaceOnUse" width="5" height="5" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="#7a6326" strokeWidth="1.4" /></pattern>
        {selected.length > 0 && <rect className="pa-series-band" x={left + selected[0] * step} y="6" width={selected.length * step} height={H - bottom - 6} />}
        {[0, top / 2, top].map(t => <g key={t}><line className="pa-grid" x1={left} x2={W - 4} y1={y(t)} y2={y(t)} /><text className="pa-axis" x={left - 6} y={y(t) + 4} textAnchor="end">{t}</text></g>)}
        {weeks.map((e, i) => {
          const x = left + i * step + 1, w = Math.max(step - 2, 1)
          const text = `SE ${e.week}/${e.year} (${formatDay(e.start)} al ${formatDay(e.end)}): ${e.value ?? (e.display === '<5' ? 'menos de 5 registros' : 'valor oculto por protección')}`
          const height = e.value ? H - bottom - y(e.value) : 0
          return <g key={`${e.year}-${e.week}`} onMouseEnter={() => setHover({ i, text })} onMouseLeave={() => setHover(null)}>
            <rect className="pa-hit" x={left + i * step} y="6" width={step} height={H - bottom - 6}><title>{text}</title></rect>
            {e.value ? <rect className="pa-bar" x={x} y={y(e.value)} width={w} height={height} rx="1.5" />
              : e.display === '<5' ? <rect x={x} y={H - bottom - 7} width={w} height="7" fill="url(#pa-hatch-series)" stroke="#7a6326" strokeWidth=".6" />
                : <rect className="pa-bar-hidden" x={x} y={H - bottom - 7} width={w} height="7" />}
          </g>
        })}
        <line className="pa-baseline" x1={left} x2={W - 4} y1={H - bottom} y2={H - bottom} />
        {weeks.length > 0 && [0, Math.floor(weeks.length / 2), weeks.length - 1].map(i => <text key={i} className="pa-axis" x={left + (i + .5) * step} y={H - 7} textAnchor="middle">SE {weeks[i].week}</text>)}
      </svg>
      {hover && <div className="pa-tooltip" role="presentation" style={{ left: `${(left + (hover.i + .5) * step) / W * 100}%` }}>{hover.text}</div>}
    </div>
    <ul className="pa-legend pa-series-legend" aria-label="Leyenda de la serie">
      <li><i className="pa-swatch" style={{ background: '#2f7f77' }} />Registros de la semana</li>
      <li><i className="pa-swatch" style={{ background: SWATCH[PROTECTED] }} />Menos de 5 (valor protegido)</li>
      <li><i className="pa-swatch pa-swatch-hidden" />Oculto para impedir deducciones</li>
      <li><i className="pa-swatch pa-swatch-band" />Bloque seleccionado</li>
    </ul>
    <details className="pa-table">
      <summary>Ver la serie semanal de {block.year} en tabla</summary>
      <div className="pa-table-scroll"><table><caption className="pa-sr">Registros semanales de la ciudad en {block.year}</caption>
        <thead><tr><th scope="col">Semana</th><th scope="col">Fechas</th><th scope="col">Registros</th></tr></thead>
        <tbody>{weeks.map(e => <tr key={`${e.year}-${e.week}`} className={e.block === block.id ? 'pa-row-selected' : undefined}>
          <th scope="row">SE {e.week}/{e.year}</th><td>{formatDay(e.start)} al {formatDay(e.end)}</td><td>{e.value ?? (e.display === '<5' ? '<5' : 'Oculto')}</td></tr>)}</tbody>
      </table></div>
    </details>
  </section>
}

export default function PublicActivity({ activity, geometry }) {
  const [index, setIndex] = useState(activity.blocks.length - 1)
  const [radio, setRadio] = useState(null)
  const block = activity.blocks[index]
  const outside = useMemo(() => new Set(activity.outside_radios || []), [activity])
  const ids = useMemo(() => geometry.features.map(f => f.properties.radio_id).sort(), [geometry])
  const counts = levelCounts(block, ids)
  const fictional = activity.source?.fictional === true
  return <div className="pa-view">
    <div className="pa-banner" role="note" data-testid="historical-banner">
      <strong>{periodBanner(activity)}</strong>
    </div>
    {fictional && <p className="pa-fixture" role="note">Datos ficticios de prueba: no corresponden a ningún lugar, persona ni fuente oficial.</p>}
    <section className="pa-controls" aria-label="Bloque de cuatro semanas">
      <div className="pa-block-select">
        <label htmlFor="pa-block">Bloque de 4 semanas epidemiológicas</label>
        <div className="pa-block-row">
          <button type="button" onClick={() => setIndex(i => Math.max(0, i - 1))} disabled={index === 0} aria-label="Bloque anterior">‹</button>
          <select id="pa-block" value={index} onChange={e => setIndex(Number(e.target.value))}>
            {activity.blocks.map((b, i) => <option key={b.id} value={i}>{blockLabel(b)} · {blockRange(b)}</option>)}
          </select>
          <button type="button" onClick={() => setIndex(i => Math.min(activity.blocks.length - 1, i + 1))} disabled={index === activity.blocks.length - 1} aria-label="Bloque siguiente">›</button>
        </div>
      </div>
      <dl className="pa-facts">
        <div><dt>Bloque seleccionado</dt><dd data-testid="block-range">{blockLabel(block)} · {blockRange(block)}</dd></div>
        <div><dt>Período del conjunto</dt><dd data-testid="period">{periodText(activity)}</dd></div>
        <div><dt>Radios con nivel publicado</dt><dd>{counts.bajo + counts.medio + counts.alto} de {ids.length - outside.size}</dd></div>
      </dl>
    </section>
    <div className="pa-layout">
      <ActivityMap geometry={geometry} block={block} outside={outside} radio={radio} onRadio={setRadio} />
      <aside className="pa-side">
        <RadioDetail ids={ids} block={block} outside={outside} radio={radio} onRadio={setRadio} />
        <div className="pa-explain">
          <p><strong>Datos agregados por zona; no muestran domicilios.</strong> Cada color abarca un radio censal completo. La ubicación de cada registro se asignó de forma aproximada.</p>
          <p>Una zona protegida o sin nivel no implica ausencia de casos: sólo indica lo que fue registrado y puede publicarse sin riesgo de identificar personas.</p>
          <p>{EXCLUDED_YEAR_TEXT}</p>
        </div>
        <details className="pa-table">
          <summary>Ver niveles por radio en tabla</summary>
          <div className="pa-table-scroll"><table><caption className="pa-sr">Nivel de cada radio censal en {blockLabel(block)}</caption>
            <thead><tr><th scope="col">Radio</th><th scope="col">Nivel</th></tr></thead>
            <tbody>{ids.map(id => <tr key={id}><th scope="row">{id}</th><td>{stateLabel(stateOf(id, block, outside))}</td></tr>)}</tbody>
          </table></div>
        </details>
      </aside>
    </div>
    <CitySeries activity={activity} block={block} />
    <footer className="pa-provenance">
      <p>Fuente: {fictional ? 'datos ficticios generados para pruebas' : activity.source?.label}. Registros agregados; no son casos confirmados ni incidencia acreditada.</p>
      <p>Paquete generado el {formatDay(activity.generated_at)}{activity.authorization?.date ? ` · publicación autorizada el ${formatDay(activity.authorization.date)}` : ''}. La fecha de generación no indica que los datos sean actuales.</p>
    </footer>
  </div>
}
