# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- El equipo epidemiológico y los agentes autorizados del Ministerio de Salud realizan ingesta, limpieza, monitoreo y análisis de casos de dengue georreferenciados para apoyar la vigilancia sanitaria y la toma de decisiones.
- La ciudadanía consulta, sin privilegios administrativos, zonas agregadas de riesgo e información preventiva sin acceder a coordenadas exactas ni datos personales.

## Product Purpose

SIGARD es un prototipo web para centralizar datos epidemiológicos, ambientales y territoriales de La Rioja Capital, representarlos geoespacialmente y apoyar la identificación temprana de zonas que requieren atención. Debe facilitar tanto el trabajo operativo del equipo epidemiológico como el acceso ciudadano oportuno a información sanitaria protegida.

## Positioning

La propuesta combina en una misma plataforma ingesta epidemiológica, análisis geoespacial, predicción temporal y comunicación pública diferenciada por rol. La experiencia ciudadana transforma ubicaciones sensibles en superficies agregadas; la experiencia administrativa reserva el detalle georreferenciado para personal autorizado y auditable.

## Operating Context

- El equipo epidemiológico carga y procesa registros de casos con coordenadas, consulta detalle territorial, monitorea patrones y utiliza los resultados como complemento de los protocolos oficiales de vigilancia.
- La ciudadanía debe ingresar directamente a un mapa de calor agregado, comprender el nivel de riesgo de su zona y acceder a recomendaciones preventivas.
- El alcance territorial del prototipo es La Rioja Capital.
- Las fuentes previstas incluyen datos epidemiológicos oficiales, variables climáticas y cartografía pública.

## Capabilities and Constraints

- Módulos comprometidos por el anteproyecto: ingesta y procesamiento; modelo predictivo; geolocalización y visualización; alertas; gestión de usuarios por roles; información sanitaria administrable.
- El acceso a datos detallados requiere autenticación y autorización por rol. Las consultas administrativas sensibles deben quedar auditadas.
- La vista ciudadana debe aplicar agregación espacial mediante densidad kernel u otra representación equivalente que impida inferir coordenadas individuales antes de renderizar el mapa.
- Las coordenadas exactas, datos personales y registros detallados nunca deben enviarse a rutas o bundles públicos.
- El frontend público está previsto para Vercel; FastAPI, PostgreSQL/PostGIS y los procesos de entrenamiento se despliegan por separado.
- En la versión actual del repositorio, los totales observados de Capital, las asignaciones sintéticas por radio y las predicciones del modelo son entidades distintas y deben permanecer visual y conceptualmente separadas.
- Mientras el componente espacial se alimente de simulaciones, debe identificarse como experimental y no presentarse como incidencia, probabilidad epidemiológica validada ni ubicación real de casos.

## Brand Commitments

- Nombre: SIGARD — Sistema informático para la geolocalización y alerta de zonas de riesgo por dengue en La Rioja Capital.
- Voz institucional, clara, sobria y accesible; sin alarmismo ni promesas de precisión no demostrada.
- La protección de datos personales y la diferenciación entre información observada, sintética y predictiva deben ser evidentes en cada superficie relevante.

## Evidence on Hand

- Anteproyecto académico 2026: `C:\Users\santi\OneDrive\Documentos\Anteproyecto- Dominguez-Molina.md`.
- Metodología y contratos vigentes del prototipo en `docs/`.
- Datos estáticos procesados de demostración en `frontend/public/data/`.
- No hay en el repositorio datos de casos individuales georreferenciados autorizados para exposición pública. Las superficies que representen esa capacidad deben utilizar datos simulados claramente rotulados hasta contar con un acuerdo institucional y datos habilitados.

## Product Principles

1. Privacidad por arquitectura: la experiencia pública recibe únicamente información agregada y no reversible.
2. Claridad de procedencia: observaciones, simulaciones y predicciones se distinguen antes de cualquier interpretación.
3. Mapa primero para la ciudadanía: la situación territorial agregada debe comprenderse apenas se ingresa.
4. Operación eficiente para epidemiología: ingesta, control de calidad, monitoreo y análisis priorizan trazabilidad y rapidez.
5. Complemento institucional: SIGARD apoya la vigilancia y la prevención; no reemplaza protocolos ni umbrales sanitarios oficiales.

## Accessibility & Inclusion

La interfaz debe funcionar con teclado, ofrecer estados de foco visibles, mantener contraste suficiente y no depender exclusivamente del color para comunicar riesgo, procedencia o condición experimental.
