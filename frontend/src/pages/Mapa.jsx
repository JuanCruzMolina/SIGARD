import { MethodNotice, PageIntro, RiskMap } from '../components/SigardComponents'
export default function Mapa({ data }) { return <div className="content-wrap"><PageIntro eyebrow="Exploración territorial" title="Mapa de riesgo"><p>Seleccioná un radio para consultar su predicción y nivel de riesgo relativo.</p></PageIntro><MethodNotice>{data.summary.data_scope}</MethodNotice><RiskMap geojson={data.geojson} /></div> }

