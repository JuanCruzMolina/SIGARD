import { useEffect, useId, useMemo, useState } from 'react'
import { GeoJSON, MapContainer, useMap } from 'react-leaflet'
import L from 'leaflet'
import { formatDate, formatDateRange, formatNumber, levelColors, levelLabel } from '../services/sigardData'
import 'leaflet/dist/leaflet.css'
import { differenceColor, experimentalColor } from '../services/experimentalContract.mjs'

// Same city center as HealthFacilitiesMap and CitizenReportForm; independent of rural polygon extents.
const researchInitialView = { center: [-29.418, -66.856], zoom: 13 }

export function PageIntro({ title, children }) { return <div className="page-intro"><div><h1>{title}</h1>{children}</div></div> }
export function MethodNotice({ children, title = 'Nota metodológica' }) { return <aside className="method-notice"><svg className="notice-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 10.5v6M12 7.5h.01" /></svg><div><strong>{title}</strong><p>{children}</p></div></aside> }
export function StatCard({ label, value, detail, accent = '' }) { return <article className={`stat-card ${accent}`}><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</article> }

export function TemporalControls({ weeks, selectedCutoffDate, onCutoffChange, selectedWeek, territorialView, onViewChange, showView = true }) {
  return <section className="data-controls" aria-label="Controles de visualización"><div className="week-control"><label htmlFor="cutoff-week">Semana de corte</label><select id="cutoff-week" value={selectedCutoffDate} onChange={(event) => onCutoffChange(event.target.value)}>{weeks.map((week) => <option key={week.cutoff_date} value={week.cutoff_date}>{formatDate(week.cutoff_date)}</option>)}</select><small>Semana objetivo: {formatDateRange(selectedWeek.target_week_start, selectedWeek.target_week_end)}</small></div>{showView && <div className="view-control"><span>Vista territorial</span><div className="segmented"><button type="button" aria-pressed={territorialView === 'context'} onClick={() => onViewChange('context')}>Contexto territorial</button><button type="button" aria-pressed={territorialView === 'simulation'} onClick={() => onViewChange('simulation')}>Simulación espacial</button></div></div>}</section>
}

export function LevelLegend({ view }) { const title = view === 'context' ? 'Contexto territorial relativo' : 'Nivel relativo experimental'; const note = view === 'context' ? 'Clasificación relativa por percentil. No corresponde a un umbral sanitario oficial.' : 'Mayor nivel = mayor señal relativa de aparición dentro de la simulación espacial. No representa una probabilidad epidemiológica validada.'; return <div className="risk-legend" aria-label={title}><strong>{title}</strong>{Object.entries(levelColors).map(([key, color]) => <span key={key}><i style={{ backgroundColor: color }} />{levelLabel(key)}</span>)}<small>{note}</small></div> }
function FitBounds({ bounds }) { const map = useMap(); useEffect(() => { if (bounds?.isValid()) map.fitBounds(bounds, { padding: [16, 16] }) }, [bounds, map]); return null }
function ResetView({ bounds, initialView }) {
  const map = useMap()
  function reset() {
    if (initialView) map.setView(initialView.center, initialView.zoom)
    else if (bounds?.isValid()) map.fitBounds(bounds, { padding: [16, 16] })
  }
  return <button className="map-reset" type="button" onClick={reset}>Restablecer vista</button>
}

function tooltipHtml(props, view) { const value = view === 'context' ? `Percentil territorial: ${formatNumber(props.percentile, 1)}` : `Índice espacial experimental: ${formatNumber(props.experimental_spatial_score, 6)}<br/>Percentil relativo: ${formatNumber(props.percentile, 2)}`; return `<strong>Radio ${props.radio_id}</strong><br/>${value}<br/>Nivel relativo: ${levelLabel(props.relative_level)}` }

function PublicRadioFocus({ geometry }) {
  const map = useMap()
  useEffect(() => {
    if (geometry) map.fitBounds(L.geoJSON(geometry).getBounds(), { padding: [24, 24], maxZoom: 15, animate: false })
  }, [geometry, map])
  return null
}

export function TerritorialMap({ geojson, view, disclaimer, compact = false, collectionKey = '', selectedRadio, onRadioSelect, researchDetails, researchMode = 'A', showData = true, statusMessage = 'Consultando scores experimentales…' }) {
  const [selected, setSelected] = useState(null)
  const controlId = useId()
  const bounds = useMemo(() => geojson ? L.geoJSON(geojson).getBounds() : null, [geojson])
  const selectionKey = `${view}-${collectionKey || geojson.features[0]?.properties?.cutoff_date || 'stable'}`
  const selectedFeature = !showData ? null : geojson.features.find(feature => feature.properties.radio_id === (selectedRadio !== undefined ? selectedRadio : selected))
  const selectedProps = selectedFeature?.properties
  const publicSelection = view !== 'research' && !compact
  const radios = useMemo(() => publicSelection ? [...geojson.features].sort((a, b) => a.properties.radio_id.localeCompare(b.properties.radio_id)) : [], [geojson, publicSelection])
  function selectRadio(id) {
    setSelected(id || null)
    onRadioSelect?.(id || null)
  }
  const initialView = view === 'research' ? researchInitialView : null
  if (!bounds?.isValid()) return <div className="error-state" role="alert">No fue posible cargar los datos del prototipo.</div>
  return <div className={`map-layout ${compact ? 'compact' : ''}`}>
    <div className="map-frame">
      <MapContainer {...(initialView || { bounds })} zoomAnimation={false} scrollWheelZoom={false} className="leaflet-map">
        {!initialView && <FitBounds bounds={bounds} />}
        <ResetView bounds={bounds} initialView={initialView} />
        {showData && <GeoJSON key={selectionKey} data={geojson} style={(feature) => ({ color: '#fff', weight: 1, fillColor: view === 'research' ? researchMode === 'difference' ? differenceColor(feature.properties.difference) : experimentalColor(feature.properties.experimental_score) : levelColors[feature.properties.relative_level] || levelColors.very_low, fillOpacity: .82 })} onEachFeature={(feature, layer) => {
          layer.bindTooltip(view === 'research' ? researchTooltip(feature.properties, researchMode) : tooltipHtml(feature.properties, view), { sticky: true, direction: 'top' })
          // These views have a textual selector; avoid 263 tooltip-only tab stops.
          if (!compact) layer.on('add', () => layer.getElement()?.setAttribute('tabindex', '-1'))
          layer.on({ mouseover: (e) => e.target.setStyle({ weight: 2.5, fillOpacity: .96 }), mouseout: (e) => e.target.setStyle({ weight: 1, fillOpacity: .82 }), click: () => selectRadio(feature.properties.radio_id) })
        }} />}
        {!compact && selectedFeature && <>
          <PublicRadioFocus geometry={selectedFeature.geometry} />
          <GeoJSON key={`selection-${selectionKey}-${selectedProps.radio_id}`} data={selectedFeature} interactive={false} style={{ color: '#123a3d', weight: 3, dashArray: '6 4', fill: false }} />
        </>}
      </MapContainer>
      {view === 'research' ? <ResearchLegend mode={researchMode} /> : <LevelLegend view={view} />}
    </div>
    {!compact && <aside className="map-side-panel">
      {publicSelection && <div className="public-radio-control week-control">
        <label htmlFor={`${controlId}-radio`}>Consultar un radio censal</label>
        <select id={`${controlId}-radio`} value={selectedProps?.radio_id || ''} onChange={(event) => selectRadio(event.target.value)} disabled={!showData} aria-describedby={`${controlId}-help`} aria-controls={`${controlId}-details`}>
          <option value="">Seleccioná un radio</option>
          {radios.map(({ properties }) => <option key={properties.radio_id} value={properties.radio_id}>Radio {properties.radio_id}</option>)}
        </select>
        <small id={`${controlId}-help`}>{radios.length} radios disponibles. Podés elegir un código con el teclado o seleccionar su polígono en el mapa.</small>
      </div>}
      <div id={`${controlId}-details`} aria-live="polite" aria-atomic="true">
        {!showData ? <p role="status" className="empty-panel">{statusMessage}</p> : selectedProps ? view === 'research' ? <div className="radio-details"><h2>Radio {selectedProps.radio_id}</h2>{researchDetails}</div> : <RadioDetails props={selectedProps} view={view} disclaimer={disclaimer} /> : <div className="empty-panel"><svg className="empty-map-icon" viewBox="0 0 32 32" aria-hidden="true"><path d="m3 7 8-3 10 3 8-3v21l-8 3-10-3-8 3Z" /><path d="M11 4v21M21 7v21" /></svg><strong>Seleccioná un radio</strong><p>{publicSelection ? 'Elegí un código en el selector o un polígono en el mapa para consultar los datos agregados de esta capa.' : 'Elegí un radio en el selector o hacé clic en el mapa para comparar A/B y consultar su historial.'}</p></div>}
      </div>
    </aside>}
  </div>
}

function Detail({ label, children }) { return <div><dt>{label}</dt><dd>{children}</dd></div> }
function scenarioLabel(value) { return value === 'spatial_clusters' ? 'Escenario espacial agrupado' : value }
export function RadioDetails({ props, view, disclaimer }) { return <div className="radio-details"><h2>Radio {props.radio_id}</h2><div className="risk-pill" style={{ backgroundColor: levelColors[props.relative_level] }}>Nivel relativo: {levelLabel(props.relative_level)}</div><dl>{view === 'context' ? <><Detail label="Código del radio">{props.radio_id}</Detail><Detail label="Población">{formatNumber(props.population, 0)}</Detail><Detail label="Densidad poblacional">{formatNumber(props.population_density, 2)}</Detail><Detail label="Hogares">{formatNumber(props.households, 0)}</Detail><Detail label="Viviendas">{formatNumber(props.dwellings, 0)}</Detail><Detail label="Superficie">{formatNumber(props.area_km2, 2)} km²</Detail><Detail label="Percentil territorial">{formatNumber(props.percentile, 1)}</Detail><Detail label="Nivel relativo">{levelLabel(props.relative_level)}</Detail>{props.territorial_context_score !== undefined && <Detail label="Índice de contexto territorial">{formatNumber(props.territorial_context_score, 3)}</Detail>}</> : <><Detail label="Código del radio">{props.radio_id}</Detail><Detail label="Semana objetivo">{formatDateRange(props.target_week_start, props.target_week_end)}</Detail><Detail label="Índice espacial experimental">{formatNumber(props.experimental_spatial_score, 6)}</Detail><Detail label="Percentil">{formatNumber(props.percentile, 1)}</Detail><Detail label="Nivel relativo">{levelLabel(props.relative_level)}</Detail><Detail label="Escenario sintético">{scenarioLabel(props.synthetic_scenario)}</Detail></>}</dl><p className="muted">{disclaimer}</p></div> }

export function TopRadios({ geojson }) { const sorted = [...geojson.features].sort((a, b) => b.properties.percentile - a.properties.percentile).slice(0, 5); return <div className="top-radios">{sorted.map((feature, index) => <div key={feature.properties.radio_id}><span>{String(index + 1).padStart(2, '0')}</span><strong>Radio {feature.properties.radio_id}</strong><em>Percentil {formatNumber(feature.properties.percentile, 1)} · {levelLabel(feature.properties.relative_level)}</em></div>)}</div> }

export function BacktestChart({ rows }) { const series=[['official_cases','Oficial','real'],['rf_minimal_climate_log_delta_prediction','Random Forest','pred'],['persistence_baseline_prediction','Persistencia','base']]; const max=Math.max(...rows.flatMap((row)=>series.map(([key])=>row[key])),1); const points=(key)=>rows.map((row,i)=>`${54+i*(620/Math.max(rows.length-1,1))},${205-(row[key]/max)*165}`).join(' '); return <div className="chart-wrap"><div className="chart-legend">{series.map(([,label,cls])=><span key={label}><i className={`line-${cls}`} />{label}</span>)}</div><svg viewBox="0 0 720 245" role="img" aria-label="Comparación temporal entre casos oficiales, Random Forest y persistencia"><line x1="48" y1="205" x2="690" y2="205" stroke="currentColor" opacity=".2" />{series.map(([key,,cls])=><polyline key={key} points={points(key)} className={`${cls}-line`} fill="none" />)}{rows.map((row,i)=><text key={row.cutoff_date} x={54+i*(620/Math.max(rows.length-1,1))} y="230" textAnchor="middle">{formatDate(row.cutoff_date).slice(0,5)}</text>)}</svg></div> }

function researchTooltip(props, mode) {
  const element = document.createElement('span')
  const value = mode === 'difference' ? props.difference : props.experimental_score
  const available = mode === 'difference' ? value !== null : props.score_status === 'available'
  const label = mode === 'difference' ? 'Diferencia B − A' : `Score ${mode}`
  element.textContent = `Radio ${props.radio_id} · ${label}: ${available ? `${value > 0 && mode === 'difference' ? '+' : ''}${formatNumber(value, 6)}` : 'Sin resultado disponible'}`
  return element
}
function ResearchLegend({ mode }) {
  const difference = mode === 'difference'
  const levels = difference
    ? [[-.75, '−1 a <−0,5'], [-.25, '−0,5 a <0'], [0, '0 · iguales'], [.25, '>0 a 0,5'], [.75, '>0,5 a 1']]
    : [[0, '0 a <0,25'], [.25, '0,25 a <0,5'], [.5, '0,5 a <0,75'], [.75, '0,75 a 1']]
  const color = difference ? differenceColor : experimentalColor
  return <div className="risk-legend research-legend" aria-label={difference ? 'Escala divergente de diferencia B menos A' : 'Escala de score experimental'}>
    <strong>{difference ? 'Diferencia B − A · escala fija −1 a +1' : `Score del Modelo ${mode} · escala fija 0 a 1`}</strong>
    {levels.map(([value, label]) => <span key={value}><i style={{ backgroundColor: color(value) }} />{label}</span>)}
    <span><i style={{ backgroundColor: color(null) }} />Sin resultado disponible</span>
    <small>{difference ? 'Negativo: B menor · positivo: B mayor. Sólo resta de scores; no es un cambio sanitario.' : 'Mismos intervalos en A y B. Scores sin calibración epidemiológica; no son umbrales sanitarios.'} Ausencia de resultado no significa cero ni ausencia de casos.</small>
  </div>
}
