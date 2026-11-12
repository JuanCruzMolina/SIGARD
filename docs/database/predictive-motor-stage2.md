# Motor predictivo de investigación: presencia y cantidad, h=1

> Cierre de etapa 4: esta campaña y sus decisiones están congeladas. El arranque
> web utiliza únicamente las referencias seleccionadas; no entrena candidatos.
> Ver [módulo final y estados activos/archivados](../predictive-module-final.md).

Esta campaña usa exclusivamente el dataset consolidado de la etapa 1, con
política nueva y máscara común. No toma etiquetas de los experimentos A/B/V3
anteriores ni cambia sus resultados. No crea rutas públicas o predicciones
operativas. Los conteos son registros elegibles SIGARD con asignaciones
territoriales experimentales; no son episodios clínicos ni incidencia.

## Alcance activo y arquitectura

El único punto de entrada de entrenamiento de esta campaña es
`sigard_ml.forecasting.motor_campaign`. Hay dos familias y un horizonte:

- Presencia: `rf_A_reference`, `rf_A_epi_climate` y `rf_A_epi_no_climate`.
  Son el mismo Random Forest de A, con tres conjuntos de variables fijados.
  `rf_A_epi_climate` es la variante mejorada solicitada, **no el B histórico**.
- Cantidad: `residual_h1`, corrección de la última semana cerrada mediante el
  regresor residual V3 de pérdida cuadrática, parámetros fijos y contracción 0,5.
  El conteo es `max(0, persistencia + 0.5 * residuo_estimado)`, sin multiplicar
  por una probabilidad de presencia.

El registro rechaza métodos distintos. B histórico, Poisson directo, hurdle,
horizontes 2/4, búsquedas de parámetros y combinaciones de modelos quedan fuera
de esta campaña. Sus implementaciones y entradas históricas se conservan para
consulta/reproducción explícita; no se invocan al entrenar el motor nuevo.

## Variables y contrato temporal

Las siete columnas de A conservan el esquema territorial/estacional. Población
y densidad utilizan la disponibilidad as-of de etapa 1: no se sustituye un
faltante por población 2022 retrospectiva. Área y grafo describen las unidades
fijas del estudio; su disponibilidad histórica institucional no está acreditada.
Una columna totalmente desconocida sigue siendo no informativa; el adaptador
existente del regresor puede usar un cero computacional constante para evitar
el fallo de binning, aprendido sólo en entrenamiento. No representa un conteo.

La variante mejorada añade conteo/presencia en origen cerrado, rezagos exactos
de una a cuatro semanas, medias de dos/cuatro semanas completas, tendencia,
número de semanas conocidas y actividad del grafo inducido común en origen.
Un hueco no se salta ni se rellena con cero. La ablación conserva exactamente
las variables estáticas y epidemiológicas, retirando sólo clima.

Clima: temperatura, humedad y precipitación del origen, rezago de una semana,
media de temperatura/suma de precipitación de cuatro semanas, medias históricas
estrictamente anteriores desde 2015 y anomalía térmica respecto de esa historia.
Una observación de un punto sigue siendo contexto compartido, no estaciones
independientes en cada radio. No se usan coordenadas, IDs numéricos, fuentes
individuales, futuras clasificaciones ni el objetivo como variables predictoras.

Los predictores utilizan mediciones hasta el cierre del origen; el objetivo es
la semana siguiente. La falta de constancia de llegada/revisión histórica
impide denominar el ejercicio validación prospectiva o as-of institucional.
Los timestamps originales no se inventan. La unidad es radio–semana, con la
misma máscara y los mismos objetivos conocidos para ambas capacidades.

## Protocolo fijado antes del ajuste

`motor_protocol.py` fija versión, variables, semillas, parámetros, bloques,
calibración, umbrales y criterios. El primer registro de PostgreSQL y
`protocol-before-fit.private.json` se escriben antes del primer fit real.
Se verifican hashes de código entre bloques.

2020 proporciona historia inicial. Se evalúan 2021/2022/2023 mediante cuatro
bloques consecutivos de 13 semanas objetivo por año, con historia expansiva.
Todos los radios de una semana permanecen juntos. Las etiquetas del ajuste
deben terminar estrictamente antes del primer origen evaluado menos cuatro
semanas; se conservan los cortes exactos por modelo. Los antecedentes durante
un bloque usan las observaciones disponibles hasta cada origen, también para
los baselines. No hay partición aleatoria de filas.

La decisión se fija sólo con esos años. Después se evalúa 2024 con el mismo
walk-forward y criterios congelados: sus primeros bloques pueden alimentar
ajustes de bloques posteriores, siempre con la purga prescrita. **2024 ya fue
observado y no se denomina test externo independiente.** Su resultado no cambia
la selección. El refit final sólo se realiza para ML seleccionado; si la salida
elegida es un baseline, se guardan estadísticas suficientes y no se afirma
que haya un estimador ML entrenado para esa salida.

## Calibración, umbrales y referencias

Se reservan hasta 26 semanas internas cronológicas: primeras 13 candidatas para
sigmoid y últimas 13 para umbral. También se purga entre resultados de
calibración y orígenes de selección de umbral. La base se ajusta únicamente con
etiquetas anteriores al primer origen interno menos cuatro semanas.

El protocolo exige clases, semanas positivas y cantidades mínimas explícitas.
Son controles computacionales, no acreditación de potencia científica. Si no
hay soporte se conserva score bruto y umbral 0,5 fijado de antemano. Cuando hay
soporte, se elige F1 entre once umbrales prefijados con FPR <=0,20, exclusivamente
en la partición interna; un calibrador nunca usa el objetivo externo. Una
calibración temporal ajustada tampoco convierte el score en riesgo sanitario
acreditado.

Presencia compara contra persistencia binaria del último cierre, prevalencia
global, prevalencia territorial suavizada y referencia territorial/estacional.
Las medias/suavizados usan sólo etiquetas de entrenamiento; el calendario del
objetivo es conocido al origen. Cantidad compara contra último cierre,
persistencia histórica de una semana anterior y media territorial entrenada.
El respaldo ante origen faltante es esa media de entrenamiento, sin inventar
observaciones. Las salidas de persistencia se identifican como baselines.

## Criterios de decisión y métricas

Presencia mejorada exige Brier al menos 3 % menor que A reentrenado y todas las
referencias simples, sin pérdida de AP mayor a 0,01 o F1 mayor a 0,03. Debe ganar
en al menos dos de tres años, no superar 1,10 del Brier de la referencia por año
con tolerancia absoluta 0,0001 y tener diferencia pareada favorable bajo el
bootstrap temporal descriptivo prefijado. A de referencia puede conservarse
sólo si pasa las mismas condiciones frente a los baselines. Si ninguna variante
las cumple, se elige el baseline con menor Brier de desarrollo. En un empate
entre mejoradas aprobadas se prefiere la variante sin clima.

Cantidad exige MAE al menos 3 % menor que **las tres** referencias, RMSE <=1,02,
control de sesgo, errores positivos y ceros, MAE de cantidades altas y RMSE de
semanas de actividad alta <=1,05 de la referencia. Debe ganar en dos años, no
exceder 1,10 de MAE por año y tener intervalo temporal pareado favorable.
Los umbrales de actividad alta se calculan sólo en entrenamiento. Si falla,
queda persistencia del último cierre como salida de referencia, sin promoción
del residual. Todos los umbrales numéricos están en el protocolo.

Se calculan Brier, AP, ROC-AUC con ambas clases, precisión, recall, F1, matriz,
FP/FN y fiabilidad descriptiva, además de MAE/RMSE/sesgo por ceros, actividad y
cola. Hay resultados por año, semana y radio. El ranking semanal de diez zonas
usa crédito fraccional ante empates y distingue nuevas activaciones respecto
del origen de supuestas primeras infecciones. Los intervalos remuestrean
bloques de cuatro semanas completas con todos los radios pareados; son
incertidumbre interna descriptiva, no muestras independientes ni confirmación
externa. El aporte climático es la diferencia pareada con/sin clima, sin otra
búsqueda o familia de modelos.

## Persistencia, artefactos y ejecución

La migración aditiva `20261102_epi15` crea `analytics.motor_campania`,
`motor_modelo`, `motor_evaluacion` y `motor_prediccion`, sin alterar tablas
anteriores. Registra dataset/política mediante FK, protocolo, entorno, hashes,
semilla, períodos de ajuste, bytes y metadatos de artefactos, predicciones,
umbrales, métricas, comparación y decisión experimental. Los triggers bloquean
UPDATE/DELETE y predicciones sin cuatro métodos registrados y purgados o fuera
de cobertura. Los esquemas siguen siendo privados.

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.motor_campaign --connection CONNECTION_PRIVADA --config CONFIG_ETAPA2_PRIVADA --output CARPETA_NUEVA_PRIVADA
```

La configuración exige permiso explícito de entrenamiento de etapa 2, versión
y hash exactos de etapa 1, referencia y fundamento de autorización. Las lecturas
de matrices y ajustes se realizan bajo guarda contra fuentes tabulares.
No se reimporta ni se cambian fuentes. La ejecución no arranca servicios o
frontend y utiliza exclusivamente el clúster WSL propio en 55439.

Los resultados reales se conservan exclusivamente en almacenamiento privado
excluido de Git. Hay artefactos por bloque, prueba de ida/vuelta de serialización,
matrices/predicciones derivadas, registro de pliegues, decisión previa a 2024,
informe final y huellas de conservación. No se modifica frontend, no se conecta
Supabase y no se inicia la etapa 3.
