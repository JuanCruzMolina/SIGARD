import { useEffect, useMemo, useState } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import { formatDate, formatNumber, getPredictedCases, getRadioId, getRadioProperties, getRisk, riskColors, riskLabel } from '../services/sigardData'
import 'leaflet/dist/leaflet.css'

const RISK_DISCLAIMER = 'Clasificación relativa dentro de la semana seleccionada. No corresponde a un umbral sanitario oficial.'

export function PageIntro({ eyebrow, title, children }) {
  return <div className="page-intro"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{children && <p>{children}</p>}</div></div>
}

export function MethodNotice({ children }) {
  return <aside className="method-notice"><span className="notice-icon">i</span><div><strong>Nota metodológica</strong><p>{children}</p></div></aside>
}

export function StatCard({ label, value, detail, accent = '' }) {
  return <article className={`stat-card ${accent}`}><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</article>
}

export function RiskLegend() {
  return <div className="risk-legend" aria-label="Leyenda de niveles de riesgo relativo">{Object.entries(riskColors).map(([key, color]) => <span key={key}><i style={{ backgroundColor: color }} />{riskLabel(key)}</span>)}</div>
}

function FitBounds({ bounds }) {
  const map = useMap()
  useEffect(() => {
    if (bounds && bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16] })
  }, [bounds, map])
  return null
}

function ResetView({ bounds }) {
  const map = useMap()
  return <button className="map-reset" type="button" onClick={() => { if (bounds && bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16] }) }}>Restablecer vista</button>
}

function tooltipHtml(props) {
  return `<strong>Radio ${getRadioId(props)}</strong><br/>Población: ${formatNumber(props.population, 0)}<br/>Densidad poblacional: ${formatNumber(props.population_density, 2)}<br/>Casos estimados: ${formatNumber(getPredictedCases(props), 3)}<br/>Nivel relativo estimado: ${riskLabel(getRisk(props))}`
}

export function RiskMap({ geojson, compact = false, onSelect }) {
  const [selected, setSelected] = useState(null)
  const bounds = useMemo(() => (geojson ? L.geoJSON(geojson).getBounds() : null), [geojson])

  const styleFor = (feature) => ({
    color: '#ffffff',
    weight: 1,
    fillColor: riskColors[getRisk(feature.properties)] || riskColors.very_low,
    fillOpacity: 0.72,
  })

  const onEachFeature = (feature, layer) => {
    const props = getRadioProperties(feature)
    layer.bindTooltip(tooltipHtml(props), { sticky: true, direction: 'top' })
    layer.on({
      mouseover: (event) => event.target.setStyle({ weight: 2.5, fillOpacity: 0.92 }),
      mouseout: (event) => event.target.setStyle({ weight: 1, fillOpacity: 0.72 }),
      click: () => {
        const radio = { feature, props, risk: getRisk(props) }
        setSelected(radio)
        onSelect?.(radio)
      },
    })
  }

  if (!bounds || !bounds.isValid()) return null

  return <div className={`map-layout ${compact ? 'compact' : ''}`}>
    <div className="map-frame">
      <MapContainer bounds={bounds} scrollWheelZoom={false} className="leaflet-map">
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <FitBounds bounds={bounds} />
        <ResetView bounds={bounds} />
        <GeoJSON data={geojson} style={styleFor} onEachFeature={onEachFeature} />
      </MapContainer>
      <RiskLegend />
    </div>
    {!compact && <aside className="map-side-panel">{selected ? <RadioDetails radio={selected} /> : <div className="empty-panel"><span className="panel-cross">+</span><strong>Seleccioná un radio</strong><p>Hacé clic sobre un radio del mapa para ver el detalle de la predicción.</p></div>}</aside>}
  </div>
}

export function RadioDetails({ radio }) {
  const { props, risk } = radio
  return <div className="radio-details">
    <span className="eyebrow">Detalle del radio</span>
    <h2>Radio {getRadioId(props)}</h2>
    <div className="risk-pill" style={{ backgroundColor: riskColors[risk] }}>Nivel relativo estimado: {riskLabel(risk)}</div>
    <dl>
      <div><dt>Código del radio</dt><dd>{getRadioId(props)}</dd></div>
      <div><dt>Población</dt><dd>{formatNumber(props.population, 0)}</dd></div>
      <div><dt>Densidad poblacional</dt><dd>{formatNumber(props.population_density, 2)}</dd></div>
      <div><dt>Casos estimados</dt><dd>{formatNumber(getPredictedCases(props), 3)}</dd></div>
      <div><dt>Casos estimados (redondeado)</dt><dd>{formatNumber(props.predicted_cases_rounded, 0)}</dd></div>
      <div><dt>Nivel relativo estimado</dt><dd>{riskLabel(risk)}</dd></div>
      <div><dt>Semana objetivo</dt><dd>{formatDate(props.prediction_week_start)} – {formatDate(props.prediction_week_end)}</dd></div>
    </dl>
    <p className="muted">{RISK_DISCLAIMER}</p>
  </div>
}

export function BacktestChart({ weeks }) {
  const values = weeks || []; const max = Math.max(...values.flatMap((w) => [w.department_cases_official, w.department_cases_predicted_from_radio_sum]), 1)
  return <div className="chart-wrap"><div className="chart-legend"><span><i className="line-real" />Real oficial</span><span><i className="line-pred" />Predicho</span></div><svg viewBox="0 0 720 250" role="img" aria-label="Comparación de casos reales y predichos por semana"><line x1="48" y1="210" x2="700" y2="210" stroke="currentColor" opacity=".2" />{values.map((w, i) => { const x = 74 + i * (610 / Math.max(values.length - 1, 1)); const realY = 210 - (w.department_cases_official / max) * 170; const predY = 210 - (w.department_cases_predicted_from_radio_sum / max) * 170; return <g key={w.cutoff_date}><circle cx={x} cy={realY} r="4" className="real-point" /><circle cx={x} cy={predY} r="4" className="pred-point" /><text x={x} y="232" textAnchor="middle">{w.cutoff_date.slice(5)}</text>{i > 0 && <><line x1={x - 610 / Math.max(values.length - 1, 1)} y1={210 - (values[i - 1].department_cases_official / max) * 170} x2={x} y2={realY} className="real-line" /><line x1={x - 610 / Math.max(values.length - 1, 1)} y1={210 - (values[i - 1].department_cases_predicted_from_radio_sum / max) * 170} x2={x} y2={predY} className="pred-line" /></>}</g> })}</svg></div>
}

export function TopRadios({ radios }) { return <div className="top-radios">{radios?.slice(0, 5).map((radio, i) => <div key={radio.radio_id}><span>{String(i + 1).padStart(2, '0')}</span><strong>Radio {radio.radio_id}</strong><em>{formatNumber(radio.predicted_cases, 3)}</em></div>)}</div> }

