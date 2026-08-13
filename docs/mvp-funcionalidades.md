# Funcionalidades del MVP de SIGARD

## Propósito

SIGARD es un MVP académico que permite consultar una estimación **temporal**
de casos de dengue para la semana siguiente en el Departamento Capital de La
Rioja y explorar información territorial asociada a sus radios censales.

El MVP valida la publicación y visualización de artefactos reproducibles. No
debe utilizarse para tomar decisiones sanitarias: la componente territorial
dinámica es una simulación experimental y no una predicción espacial validada.

## Qué puede hacer una persona usuaria

### 1. Consultar el resumen del período seleccionado

La pantalla **Resumen SIGARD** presenta, para cada corte de datos disponible:

- la semana epidemiológica objetivo;
- la cantidad esperada de casos en Capital para la semana siguiente;
- la cantidad de radios censales incluidos (263);
- la variante del modelo y la fecha de corte;
- una vista abreviada del componente territorial elegido.

La estimación de casos corresponde a un modelo temporal Random Forest. Es una
predicción agregada para Capital, no un conteo estimado por radio censal.

### 2. Cambiar el corte temporal

El selector temporal permite elegir uno de los cortes publicados. Al cambiarlo,
el sistema actualiza en conjunto:

- el rango de la semana objetivo;
- la predicción temporal departamental;
- la simulación espacial experimental de esa misma semana, cuando está activa.

El contrato del frontend exige que estos elementos estén alineados por fecha de
corte y por inicio y fin de semana objetivo.

### 3. Explorar el mapa territorial

La pantalla **Mapa territorial** ofrece dos vistas alternativas para los 263
radios censales del Departamento Capital:

| Vista | Contenido | Uso correcto |
| --- | --- | --- |
| Contexto territorial relativo | Indicador estable derivado de población, hogares, viviendas y densidad. | Describir características relativas del territorio; no es riesgo epidemiológico. |
| Simulación espacial experimental | Índice relativo y dinámico basado en una distribución sintética de los totales semanales observados. | Demostrar el comportamiento visual y técnico del MVP; no localizar casos reales ni afirmar predicción espacial validada. |

El mapa y los listados destacados clasifican radios en niveles relativos
(`muy bajo`, `bajo`, `medio`, `alto`). Estos niveles son de visualización y no
representan umbrales sanitarios oficiales.

### 4. Consultar la validación temporal

La pantalla **Validación** muestra una evaluación exploratoria con seis semanas
de holdout temporal. Incluye:

- error absoluto medio (MAE) del Random Forest;
- MAE de un baseline de persistencia;
- reducción de MAE respecto del baseline;
- exactitud al anticipar la dirección del cambio;
- gráfico y tabla de backtest, con los casos oficiales, ambas estimaciones y
  sus errores para cada corte.

La comparación emplea cortes temporales, por lo que simula el uso futuro de un
modelo. Sus métricas evalúan sólo la predicción agregada departamental y no
validan el componente espacial.

### 5. Consultar la metodología y las advertencias

La pantalla **Metodología** explica las fuentes, el flujo de predicción
temporal, el contexto censal y la razón de usar simulación espacial. Las
advertencias metodológicas también se muestran junto a las vistas territoriales
para que los resultados sintéticos no se interpreten como evidencia
epidemiológica observada.

## Datos que consume el frontend

El MVP carga artefactos estáticos versionados desde `frontend/public/data/`:

- `available_weeks.json`: semanas y cortes disponibles; es la fuente única del
  selector temporal.
- `temporal_predictions.json`: una predicción temporal agregada por corte.
- `territorial_context.geojson`: contexto territorial real y estable.
- `experimental_spatial_history.geojson`: capa territorial sintética y
  dinámica por semana.
- `model_evaluation.json`: métricas y backtest temporal.
- `mvp_metadata.json`: identidad del MVP y advertencias que debe mostrar la
  interfaz.

Antes de mostrar la aplicación, el frontend valida que haya 263 radios y que
la predicción temporal y la capa experimental correspondan exactamente a la
misma semana objetivo.

## Límites del MVP

1. Los casos oficiales disponibles están agregados para Capital; no incluyen
   ubicaciones individuales ni observaciones por radio censal.
2. La distribución por radio y cualquier punto de visualización son sintéticos.
3. La predicción temporal agregada y la simulación espacial son componentes
   independientes: no se deben sumar ni presentar como una predicción por
   radio.
4. La evaluación actual es exploratoria y se apoya en un holdout temporal
   limitado.
5. El frontend puede desplegarse de forma independiente; el entrenamiento se
   ejecuta fuera del backend y la API sólo debe servir resultados ya generados.

## Próximo paso para evolucionar el producto

Para incorporar una predicción territorial real se necesitarían casos
epidemiológicos con referencia territorial apta para entrenamiento y validación.
Eso permitiría reemplazar la simulación espacial por un modelo evaluado contra
observaciones reales, conservando la predicción temporal departamental como un
componente complementario.
