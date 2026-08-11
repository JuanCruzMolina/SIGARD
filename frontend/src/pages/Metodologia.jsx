import { MethodNotice, PageIntro } from '../components/SigardComponents'

const FlowArrow = () => <span className="flow-arrow" aria-hidden="true">↓</span>

function DataCard({ className, title, subtitle, items, footer }) {
  return <article className={`source-card ${className}`}>
    <h3>{title}</h3>
    <strong>{subtitle}</strong>
    <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    <p>{footer}</p>
  </article>
}

export default function Metodologia() {
  return <div className="content-wrap narrow methodology-page">
    <PageIntro eyebrow="Transparencia del prototipo" title="Metodología">
      <p>SIGARD combina una predicción temporal de casos con información territorial real y una simulación espacial experimental.</p>
    </PageIntro>

    <MethodNotice title="Alcance del prototipo">
      La predicción temporal utiliza registros históricos reales para estimar los casos esperados en el departamento Capital durante la semana siguiente. El análisis territorial combina información censal y cartográfica real con una simulación espacial experimental, utilizada porque todavía no se dispone de la ubicación territorial de los casos observados.
    </MethodNotice>

    <section className="architecture" aria-labelledby="architecture-title">
      <div className="architecture-root" id="architecture-title">SIGARD</div>
      <div className="architecture-branches">
        <article className="architecture-branch temporal-branch">
          <header>Predicción temporal</header>
          <div className="flow-step">
            <strong>Datos históricos observados</strong>
            <ul>
              <li>Casos oficiales de dengue</li>
              <li>Información climática</li>
              <li>Evolución entre semanas</li>
            </ul>
          </div>
          <FlowArrow />
          <div className="flow-step compact"><strong>Random Forest</strong></div>
          <FlowArrow />
          <div className="flow-result">Casos esperados para la próxima semana en Capital</div>
        </article>

        <article className="architecture-branch territorial-branch">
          <header>Análisis territorial</header>
          <div className="territorial-components">
            <div className="territorial-component">
              <span>Contexto territorial</span>
              <strong>Datos censales y cartográficos</strong>
              <FlowArrow />
              <b>Contexto territorial relativo</b>
              <p>Describe características del territorio a partir de información real.</p>
            </div>
            <div className="territorial-component synthetic">
              <span>Simulación espacial</span>
              <strong>Casos semanales observados<br />+<br />distribución territorial simulada</strong>
              <FlowArrow />
              <b>Simulación espacial experimental</b>
              <p>Permite demostrar el comportamiento territorial del prototipo mientras no se dispone de casos georreferenciados.</p>
            </div>
          </div>
        </article>
      </div>
      <div className="architecture-convergence" aria-hidden="true"><span>↘</span><span>↙</span></div>
      <div className="flow-output">Presentación SIGARD</div>
      <p className="independence-note">La predicción temporal y el análisis territorial son componentes conceptualmente independientes que SIGARD presenta de manera conjunta.</p>
    </section>

    <section className="panel temporal-explainer">
      <span className="eyebrow">Predicción temporal</span>
      <h2>Random Forest</h2>
      <p>El modelo analiza la evolución histórica de los casos y variables climáticas para estimar la cantidad esperada de casos en el departamento Capital durante la semana siguiente.</p>
      <p>Para capturar los cambios entre semanas, el modelo aprende la variación relativa respecto del período anterior y luego reconstruye la cantidad esperada.</p>
    </section>

    <section className="panel data-origins">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Fuentes y alcance</span>
          <h2>De dónde provienen los datos</h2>
          <p>El prototipo combina información observada con datos simulados exclusivamente para el componente espacial.</p>
        </div>
      </div>
      <div className="source-grid">
        <DataCard className="observed" title="Datos observados" subtitle="Epidemiología y clima" items={['Casos históricos oficiales de dengue', 'Temperatura', 'Humedad relativa', 'Precipitaciones']} footer="Estos datos se utilizan para construir y evaluar la predicción temporal." />
        <DataCard className="territorial" title="Datos territoriales" subtitle="Censo y cartografía" items={['Población', 'Densidad poblacional', 'Hogares', 'Viviendas', 'Radios censales', 'Superficie territorial']} footer="Estos datos describen las características relativas de los 263 radios censales analizados." />
        <DataCard className="simulated" title="Datos espaciales simulados" subtitle="Experimentación territorial" items={['Asignación semanal simulada de casos entre radios censales', 'Patrones de concentración territorial simulados', 'Historial territorial experimental por semana', 'Variables temporales derivadas para la experimentación espacial', 'Índice espacial experimental']} footer="El índice espacial experimental presentado en el mapa deriva de esta estructura simulada y no constituye validación epidemiológica real." />
      </div>
      <div className="simulation-notice">
        <h3>¿Por qué se utiliza una simulación espacial?</h3>
        <p>Actualmente se dispone de casos observados a nivel departamental, pero no de la ubicación georreferenciada necesaria para entrenar y validar un modelo espacial real por radio censal. Por ese motivo, SIGARD utiliza una distribución territorial simulada para demostrar el funcionamiento espacial del prototipo sin presentarla como evidencia epidemiológica observada.</p>
        <strong>Los casos totales semanales utilizados como referencia son observados; la ubicación de esos casos dentro del territorio es la parte simulada.</strong>
      </div>
    </section>

    <section className="panel future-panel">
      <span className="eyebrow">Evolución del componente espacial</span>
      <h2>¿Qué cambiaría con datos territoriales reales?</h2>
      <div className="future-grid">
        <article>
          <h3>Prototipo actual</h3>
          <div>Casos oficiales<br />por semana y departamento</div>
          <FlowArrow />
          <strong>Predicción temporal<br />con datos observados</strong>
          <span className="future-plus">+</span>
          <div>No se conoce la ubicación<br />de cada caso</div>
          <FlowArrow />
          <div>Distribución territorial<br />simulada</div>
          <FlowArrow />
          <strong>Simulación espacial experimental</strong>
        </article>
        <article className="georeferenced">
          <h3>Con datos georreferenciados</h3>
          <div>Casos oficiales<br />con referencia territorial</div>
          <FlowArrow />
          <div>Entrenamiento del componente espacial<br />con observaciones reales</div>
          <FlowArrow />
          <strong>Validación territorial real</strong>
          <FlowArrow />
          <strong>Predicción espacial basada en datos observados</strong>
        </article>
      </div>
      <p className="future-message">La predicción temporal departamental puede continuar funcionando como un componente independiente. Los datos georreferenciados permitirían reemplazar la simulación espacial por un modelo entrenado y validado sobre observaciones territoriales reales.</p>
    </section>
  </div>
}
