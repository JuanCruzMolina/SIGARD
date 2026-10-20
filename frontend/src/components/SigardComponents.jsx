import { useEffect, useMemo, useState } from 'react'
import { GeoJSON, MapContainer, useMap } from 'react-leaflet'
import L from 'leaflet'
import { formatDate, formatDateRange, formatNumber, levelColors, levelLabel } from '../services/sigardData'
import 'leaflet/dist/leaflet.css'
import { experimentalColor } from '../services/experimentalContract.mjs'

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

export function TerritorialMap({ geojson, view, disclaimer, compact = false, collectionKey = '', selectedRadio, onRadioSelect, researchDetails, showData = true, statusMessage = 'Consultando scores experimentales…' }) {
  const [selected, setSelected] = useState(null)
  const bounds = useMemo(() => geojson ? L.geoJSON(geojson).getBounds() : null, [geojson])
  const selectionKey = `${view}-${collectionKey || geojson.features[0]?.properties?.cutoff_date || 'stable'}`
  const selectedProps = !showData ? null : view === 'research' && selectedRadio !== undefined
    ? geojson.features.find(feature => feature.properties.radio_id === selectedRadio)?.properties
    : selected?.key === selectionKey ? selected.props : null
  const initialView = view === 'research' ? researchInitialView : null
  if (!bounds?.isValid()) return <div className="error-state" role="alert">No fue posible cargar los datos del prototipo.</div>
  return <div className={`map-layout ${compact ? 'compact' : ''}`}><div className="map-frame"><MapContainer {...(initialView || { bounds })} scrollWheelZoom={false} className="leaflet-map">{!initialView && <FitBounds bounds={bounds} />}<ResetView bounds={bounds} initialView={initialView} />{showData && <GeoJSON key={selectionKey} data={geojson} style={(feature) => ({ color: '#fff', weight: 1, fillColor: view === 'research' ? experimentalColor(feature.properties.experimental_score) : levelColors[feature.properties.relative_level] || levelColors.very_low, fillOpacity: .82 })} onEachFeature={(feature, layer) => { layer.bindTooltip(view === 'research' ? researchTooltip(feature.properties) : tooltipHtml(feature.properties, view), { sticky: true, direction: 'top' }); layer.on({ mouseover: (e) => e.target.setStyle({ weight: 2.5, fillOpacity: .96 }), mouseout: (e) => e.target.setStyle({ weight: 1, fillOpacity: .82 }), click: () => { setSelected({ key: selectionKey, props: feature.properties }); onRadioSelect?.(feature.properties.radio_id) } }) }} />}</MapContainer>{view === 'research' ? <ResearchLegend /> : <LevelLegend view={view} />}</div>{!compact && <aside className="map-side-panel">{!showData ? <p role="status" className="empty-panel">{statusMessage}</p> : selectedProps ? view === 'research' ? <div className="radio-details"><h2>Radio {selectedProps.radio_id}</h2><p>Score experimental: <strong>{selectedProps.score_status === 'available' ? formatNumber(selectedProps.experimental_score, 6) : 'Sin resultado disponible'}</strong></p><p>Rezagos conocidos: {selectedProps.data_availability.known_lag_count === null ? 'No utilizados por A' : `${selectedProps.data_availability.known_lag_count}/4 (retrospectivos)`}</p>{researchDetails}<p className="muted">{disclaimer}</p></div> : <RadioDetails props={selectedProps} view={view} disclaimer={disclaimer} /> : <div className="empty-panel"><svg className="empty-map-icon" viewBox="0 0 32 32" aria-hidden="true"><path d="m3 7 8-3 10 3 8-3v21l-8 3-10-3-8 3Z" /><path d="M11 4v21M21 7v21" /></svg><strong>Seleccioná un radio</strong><p>Hacé clic sobre un radio para consultar los datos agregados de esta capa.</p></div>}</aside>}</div>
}

function Detail({ label, children }) { return <div><dt>{label}</dt><dd>{children}</dd></div> }
function scenarioLabel(value) { return value === 'spatial_clusters' ? 'Escenario espacial agrupado' : value }
export function RadioDetails({ props, view, disclaimer }) { return <div className="radio-details"><h2>Radio {props.radio_id}</h2><div className="risk-pill" style={{ backgroundColor: levelColors[props.relative_level] }}>Nivel relativo: {levelLabel(props.relative_level)}</div><dl>{view === 'context' ? <><Detail label="Código del radio">{props.radio_id}</Detail><Detail label="Población">{formatNumber(props.population, 0)}</Detail><Detail label="Densidad poblacional">{formatNumber(props.population_density, 2)}</Detail><Detail label="Hogares">{formatNumber(props.households, 0)}</Detail><Detail label="Viviendas">{formatNumber(props.dwellings, 0)}</Detail><Detail label="Superficie">{formatNumber(props.area_km2, 2)} km²</Detail><Detail label="Percentil territorial">{formatNumber(props.percentile, 1)}</Detail><Detail label="Nivel relativo">{levelLabel(props.relative_level)}</Detail>{props.territorial_context_score !== undefined && <Detail label="Índice de contexto territorial">{formatNumber(props.territorial_context_score, 3)}</Detail>}</> : <><Detail label="Código del radio">{props.radio_id}</Detail><Detail label="Semana objetivo">{formatDateRange(props.target_week_start, props.target_week_end)}</Detail><Detail label="Índice espacial experimental">{formatNumber(props.experimental_spatial_score, 6)}</Detail><Detail label="Percentil">{formatNumber(props.percentile, 1)}</Detail><Detail label="Nivel relativo">{levelLabel(props.relative_level)}</Detail><Detail label="Escenario sintético">{scenarioLabel(props.synthetic_scenario)}</Detail></>}</dl><p className="muted">{disclaimer}</p></div> }

export function TopRadios({ geojson }) { const sorted = [...geojson.features].sort((a, b) => b.properties.percentile - a.properties.percentile).slice(0, 5); return <div className="top-radios">{sorted.map((feature, index) => <div key={feature.properties.radio_id}><span>{String(index + 1).padStart(2, '0')}</span><strong>Radio {feature.properties.radio_id}</strong><em>Percentil {formatNumber(feature.properties.percentile, 1)} · {levelLabel(feature.properties.relative_level)}</em></div>)}</div> }

export function BacktestChart({ rows }) { const series=[['official_cases','Oficial','real'],['rf_minimal_climate_log_delta_prediction','Random Forest','pred'],['persistence_baseline_prediction','Persistencia','base']]; const max=Math.max(...rows.flatMap((row)=>series.map(([key])=>row[key])),1); const points=(key)=>rows.map((row,i)=>`${54+i*(620/Math.max(rows.length-1,1))},${205-(row[key]/max)*165}`).join(' '); return <div className="chart-wrap"><div className="chart-legend">{series.map(([,label,cls])=><span key={label}><i className={`line-${cls}`} />{label}</span>)}</div><svg viewBox="0 0 720 245" role="img" aria-label="Comparación temporal entre casos oficiales, Random Forest y persistencia"><line x1="48" y1="205" x2="690" y2="205" stroke="currentColor" opacity=".2" />{series.map(([key,,cls])=><polyline key={key} points={points(key)} className={`${cls}-line`} fill="none" />)}{rows.map((row,i)=><text key={row.cutoff_date} x={54+i*(620/Math.max(rows.length-1,1))} y="230" textAnchor="middle">{formatDate(row.cutoff_date).slice(0,5)}</text>)}</svg></div> }

function researchTooltip(props) {
  const element = document.createElement('span')
  element.textContent = `Radio ${props.radio_id} · Score experimental: ${props.score_status === 'available' ? formatNumber(props.experimental_score, 6) : 'Sin resultado disponible'}`
  return element
}
function ResearchLegend() {
  return <div className="risk-legend" aria-label="Escala de score experimental"><strong>Score experimental bruto</strong>{[0, .25, .5, .75].map((v, i) => <span key={v}><i style={{ backgroundColor: experimentalColor(v) }} />{v}–{(i + 1) / 4}{i === 3 ? ' (incluye 1)' : ''}</span>)}<span><i style={{ backgroundColor: experimentalColor(null) }} />Sin resultado disponible</span><small>Intervalos fijos de amplitud 0,25 sobre el score [0,1]; el límite superior pasa al intervalo siguiente. No son umbrales sanitarios ni probabilidades reales de infección. Sin resultado no significa ausencia de casos.</small></div>
}
