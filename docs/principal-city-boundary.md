# Límite censal y territorio operativo de la ciudad de La Rioja

Revisión: 22/10/2026. Adopción operativa aprobada por el responsable: **23/10/2026**.
Estado actual: **256 radios adoptados para el módulo predictivo principal**,
versión `la-rioja-46014010-256-v1`, descrita en la sección final. Se conserva
debajo la evidencia de la revisión del 22/10; sus escenarios y pendientes de
adopción describen aquel momento. No se leyeron datos individuales de pacientes
ni se modificaron etiquetas, geocodificaciones, modelos o el maestro de 263.

## Identidad y procedencia

La [capa oficial de localidades censales del INDEC](https://geonode.indec.gob.ar/layers/geonode_data:geonode:localidades_censales)
identifica una única fila con esta combinación, comprobada conjuntamente:

- Provincia: La Rioja, `cpr=46`.
- Departamento: Capital, `cde=46014`.
- Localidad: La Rioja, **`clc=46014010`**, `fna=Localidad La Rioja`.
- Tipo: **`tlc=1`, localidad simple**; `codaglo=N/A`, `aglomerado=N/A`.
- Autoridad: INDEC. `id=94913` y `fid=2115` son campos del servicio;
  la clave censal utilizada es `46014010`.

No se seleccionó por nombre solamente. Se descargaron las 71 localidades de la
provincia mediante el WFS oficial, con filtro `cpr='46'`, y se verificó que esa
fila fuera única. La capa no identifica otro componente en Capital ni atribuye
La Rioja a un aglomerado. La interpretación `tlc=1` se respalda en el
[metadato oficial, página 2](https://portalgeoestadistico.indec.gob.ar/geoportal/documents/metadato_localidades_censales.pdf):
1 es localidad simple y 2, componente de aglomerado. No se construyó un aglomerado
por proximidad ni se confundió la localidad con un gobierno local.

El metadato vincula la capa al Marco Geoestadístico del **Censo 2022**, con fecha
documental 20/12/2024; GeoNode informa publicación 29/05/2026. No es una versión
histórica acreditada para 2020–2021 ni una medición del crecimiento urbano hasta
2026. Se conserva el snapshot de bytes descargados, fecha UTC, consulta, cabeceras
disponibles y SHA-256, sin inventar una versión semántica o disponibilidad P6.
La delimitación es por continuidad física de edificaciones y vías, con fines
estadísticos; no representa por sí misma un ejido municipal legal.

No se identificó copia local previa. La incorporación de esta cartografía pública
fue autorizada expresamente para esta etapa. Los archivos nuevos y documentos
oficiales quedaron en `data/raw/territorial/indec_localidades_censales_20261022/`.
Se preservan allí las respuestas originales: no se editó ninguna fuente existente.
La consulta suplementaria de tipos de radio descargó sólo atributos oficiales de
código/tipo, sin nuevas geometrías de radios ni información sanitaria. GeoNode no
especifica licencia; se conserva la atribución requerida: INDEC (2022), Marco
Geoestadístico Nacional.

## CRS y comparación

El PDF declara EPSG:4326; GeoNode y la respuesta WFS utilizada declaran
**EPSG:3857**. Se respetó el CRS de cada respuesta, sin reasignarlo. Para superficies
ambas capas se transformaron a **EPSG:32719**, reutilizando `validate_metric_extent`
y la convención métrica existente. La localidad está dentro del área nominal de
UTM 19S; su máxima desviación de escala comprobada es 0,01762%. El departamento
excede parcialmente el área nominal, con desviación máxima 0,10097%, dentro de la
tolerancia técnica existente de 0,2%. Esa tolerancia no estima error geográfico
ni se usó como buffer o umbral de selección.

`official.cartography.compare_locality_boundary` reutiliza la validación del
maestro y añade la comparación en memoria, sin otro pipeline. La regla estricta es:

- **Interior:** la localidad cubre todo el polígono del radio (`covered_by`).
- **Parcial:** intersección de área positiva, sin cobertura completa.
- **Exterior:** intersección de área cero; un contacto sólo de borde no incorpora
  un radio. En estos archivos no hubo contactos exclusivos de borde.

No se repararon geometrías, aplicaron buffers o eliminaron fragmentos pequeños.
Se conserva el cociente bruto de áreas y otro acotado a [0,1] exclusivamente para
ruido numérico del orden de 1e-15. La clasificación no usa ese acotamiento.

La localidad tiene **107,6912 km²**. De los 263 radios del maestro:
**245 son interiores, 14 parciales y 4 exteriores**. Los mismos conteos se
obtuvieron al comprobar sólo topología en EPSG:4326 y EPSG:3857; las áreas y
proporciones se calcularon exclusivamente en EPSG:32719.

Los 14 parciales se separan en:

- **11 radios `U`**, con 99,99137% a 99,9999975% de su superficie dentro de la
  localidad. Sus remanentes exteriores van de unos 0,021 a 292,94 m². Las pequeñas
  diferencias no acreditan una causa; se requiere revisar versiones y límites.
- **`460140101` (`M` local):** 0,1076396% interior, unos 0,81909 km².
- **`460140102` (`R` local):** 0,00197786% interior, unos 13.391,49 m².
- **`460140103` (`R` local):** 0,000808205% interior, unos 19.851,14 m².

Los tres últimos tienen grandes áreas exteriores. Su pequeña proporción no
demuestra ausencia de viviendas o episodios en la parte urbana. Además, unos
**113,43 m²** del polígono de localidad quedan fuera de la unión departamental de
radios de esta versión. Se registra el remanente sin recortarlo ni completar la
cartografía automáticamente. Estas superficies son diagnósticas: no son pesos
para repartir población, casos o incertidumbre de geocodificación.

## Tipos censales y diferencias entre versiones

La [documentación censal del INDEC](https://portalgeoestadistico.indec.gob.ar/geoportal/documents/metadato_radios_censales.pdf)
define las clases del atributo de tipo: **U, urbano**, población y viviendas
agrupadas en manzanas de una localidad; **R, rural**, población y viviendas
dispersas; **M, mixto**, parte agrupada y parte rural dispersa. La
[descripción oficial de envolventes](https://geonode.indec.gob.ar/catalogue/csw_to_extra_format/5cb47ea2-8ab6-4d3d-a173-c907de2ea3b8/envolventes-de-localidades-censales.html)
explica que combinan radios urbanos y partes urbanas de mixtos. Esto resuelve la
interpretación de categorías pendiente en la revisión P5 anterior; no convierte
un radio completo mixto en territorio urbano.

La copia local contiene **256 U, 6 R y 1 M**. La consulta de atributos del servicio
actual `geonode:radios_censales2` contiene los mismos 263 IDs, pero **256 U, 4 R y
3 M**: `460140102` y `460140103` figuran ahora como **M**. No se descargaron sus
geometrías actuales, por lo que esto no prueba igualdad geométrica entre versiones
ni autoriza actualizar el maestro. Se conservaron ambos tipos en la comparación.
La diferencia debe resolverse con la procedencia/versionado censal antes de
adoptar una regla que dependa de `TIPO`. Tampoco se infiere pertenencia a la ciudad
exclusivamente por una letra de tipo.

## Reglas evaluadas y propuesta para revisión

En la revisión del 22/10, las listas siguientes eran escenarios sin aprobación:

- **Cobertura completa: 245 radios.** Núcleo estricto; cubre sólo el 82,2066% del
  polígono de localidad y su grafo inducido tiene dos componentes. Excluir todos
  los parciales también excluiría 11 radios urbanos casi completos.
- **Cualquier intersección positiva: 259 radios.** Envolvente máxima de revisión,
  con los 14 parciales explícitos. Sus radios completos suman 4.001,07 km² y
  añaden 3.893,38 km² exteriores a la ciudad. No equivale a la ciudad censal.
- **Tipo U más intersección positiva: 256 radios.** Incluye los 245 interiores y
  los 11 urbanos parciales. Cubre el 99,2084% de la localidad; deja fuera parte
  de su superficie ubicada en los tres radios restantes.
- **Mayoría de superficie, al menos 50%: 256 radios.** Coincide aquí con los U,
  pero el umbral es sólo un escenario, sin justificación epidemiológica.
- **Punto representativo interior: 256 radios.** Coincide aquí con la alternativa
  U; no valida ubicaciones de registros ni establece una regla general equivalente.
- **Centroide dentro de la localidad: 254 radios.** Muestra que elegir por un
  punto puede omitir radios casi completos de formas irregulares. No se adopta.

**Propuesta:** utilizar el polígono oficial `46014010` como definición geográfica
censal de la ciudad para revisión; distinguir el núcleo de 245 radios, los 14
parciales y los cuatro exteriores. Mantener 259 como lista máxima de candidatos
para revisar intersecciones y 256 U como alternativa de unidades completas.
No hay un único subconjunto de radios completos que reproduzca exactamente ese
polígono. La adopción exige una decisión explícita sobre los parciales, las
diferencias entre versiones y el significado del objetivo por radio. No se elige
una alternativa buscando métricas ni se sustituyen los 263 radios actuales.

## Compatibilidad y condiciones para adoptar

Los IDs se conservan como cadenas de nueve caracteres; todas las listas son
subconjuntos del maestro. El adaptador admite un universo aprobado diferente de
263, con igualdad de IDs en conteos, contexto y grafo y decisiones P5/P6 aplicables
a sus versiones. No exige geometrías como features ni valida por sí mismo límites.

Se comprobó el grafo original y se prepararon grafos inducidos **sólo como
propuestas**, cerrados y simétricos. El escenario de 256 radios elimina 46
referencias dirigidas a vecinos excluidos; el de 259 elimina cinco. Copiar sin
filtrar el grafo original dejaría referencias fuera de alcance y sería incompatible
con el contrato. Cambiar vecinos también cambia features: no se actualizó el
grafo vigente ni se recalcularon población, densidad, predicciones o modelos.

Al cierre de la revisión del 22/10 faltaba aprobar el límite censal como ámbito del estudio,
resolver versiones y los 14 parciales y documentar la regla de inclusión de
unidades completas. La preparación futura deberá versionar el universo y grafo,
conservar el sentido de conteos por radio y acreditar su adecuación temporal y
disponibilidad P6. El límite urbano no acredita coordenadas aproximadas, residencia
o lugar de contagio, ni resuelve los demás pendientes epidemiológicos de P5.
En esa revisión no se produjo un paquete real para el adaptador ni se modificaron asignaciones.

## Artefactos y validación

Resultados de revisión, excluidos de Git:
`data/interim/official/principal_city_boundary_20261022_v1/review_v2/` contiene
`proposal.json`, `radio_locality_comparison.csv` y `.parquet` (las 263 filas con
relación, tipos de ambas versiones, áreas y proporciones),
`locality_46014010.geojson` y `integrity_manifest.json`. El script puntual local
`build_proposal.py` conserva la selección y reglas exactas y reutiliza el módulo
existente; no hay otra CLI o pipeline territorial. La primera comparación queda
preservada en la carpeta padre; `review_v2` incorpora la consulta suplementaria
de tipos, sin sobrescribir aquella evidencia ni las fuentes.

Las huellas de **244 entradas protegidas** coinciden antes y después, incluidos
P2/P3, clima, P5 previo y A/B. Se verificaron las descargas contra sus manifiestos
y se fijaron las huellas de las salidas y del código utilizado. No se abrieron
Excel SISA, domicilios o coordenadas individuales; no hubo entrenamiento,
servicios, frontend/backend, publicación ni push.

Validación: **53 pruebas aprobadas, 6 excluidas**, con `_fit` y `Pipeline.fit`
bloqueados. Las nuevas pruebas usan polígonos inventados con superficies conocidas,
incluyen contactos sin área, intersecciones pequeñas, remanentes exteriores,
CRS, entradas inválidas y conservación de fuentes. Se ejecutaron las regresiones
focalizadas de cartografía, asignación incierta, IDs, grafo y adaptador.
Seguridad estática: **178 controles aprobados**; `git diff --check` sin errores.

## Adopción operativa del 23/10/2026

El responsable aprobó explícitamente la localidad oficial **46014010** como
referencia y la inclusión de **unidades completas**: los 245 radios interiores
más los 11 parciales cuya fracción de superficie interior bruta es **≥ 0,9999**.
Se comprobaron **256 IDs únicos**. No se selecciona por `TIPO`, puntos ni redondeo.
Las discrepancias de tipo entre versiones quedan registradas en la comparación
previa; no intervienen en esta regla ni se actualizan fuentes.

Se excluyeron `460140101`, `460140102`, `460140103`, `460140201`, `460140202`,
`460140301` y `460140302`. No se recortaron radios. La unión de unidades completas
continúa sin reproducir exactamente el límite de localidad; las fracciones de
superficie no reparten población ni episodios.

`ml/configs/principal_territory.json` fija decisión, versión, localidad, umbral,
conteos esperados y SHA-256 del maestro y de la comparación `review_v2`.
Se extendió el **constructor territorial existente**, sin otra CLI o pipeline,
para reutilizar esas dos entradas sin reconstruir la comparación ni abrir SISA:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.territorial --universe-config ml/configs/principal_territory.json
```

Salidas locales excluidas de Git, creadas en
`data/processed/principal_territory_46014010_256_v1/`:

- `territory.parquet`: geometrías y atributos originales de los 256 radios;
  sólo `neighbor_ids` cambia al grafo inducido.
- `graph.json`: versión, inventario completo de nodos y pares dirigidos.
- `manifest.json`: configuración/procedencia, validaciones, listas seleccionada
  y excluida y huellas de las dos salidas. Reejecutar sobre el mismo destino
  falla; nunca sobrescribe fuentes o versiones.

La población censal conservada suma **207.842 personas** y las superficies
completas **106,8393377116 km²**, en EPSG:32719. Se verificaron población entera
no negativa, área positiva consistente con la geometría, densidad
`poblacion / superficie_km2`, IDs y polígonos válidos. Se reabrió GeoParquet y se
compararon geometrías y atributos contra la selección en memoria. No se
recalcularon indicadores ni scores territoriales.

El grafo tiene **1.522 aristas dirigidas (761 pares), una componente y ningún
aislado**. Se quitaron 46 referencias dirigidas desde seleccionados hacia
excluidos. Es simétrico, sin lazos, duplicados ni referencias fuera del universo;
se contrastó con contigüidad queen mediante el validador geográfico existente.
El grafo y el maestro originales de 263 permanecen intactos.

`forecasting.adapter.territorial_components(config, root, available_on=...,
source_ref=..., graph_available_on=..., graph_ref=...)` carga la versión y
devuelve radios, `territory` (población/superficie), `graph` y el metadato de
preparación `territory_version`. Este metadato debe enlazarse en la procedencia
de territorio/grafo, sin agregar campos al esquema `principal-count-input-1`.
Las fechas de disponibilidad son explícitas: no se infieren del censo,
descarga o aprobación. No fabrica conteos, grillas, ceros ni permisos.

El adaptador es compatible con 256 unidades: una prueba ficticia recorre el
contrato y construye el panel de 256 filas sin ajuste; otras rechazan vecinos
excluidos y contexto desalineado. Para datos reales siguen pendientes P1–P6,
disponibilidad histórica, episodios y cobertura acreditados. La decisión
operativa **no completa P5 epidemiológico**, no acredita precisión, residencia
o lugar de infección ni idoneidad histórica del Censo 2022 para 2020–2021.
Las geocodificaciones aproximadas y advertencias permanecen intactas;
no se reasignaron pacientes ni se creó un paquete epidemiológico real.

Validación actual: **237 pruebas aprobadas, 3 excluidas** (recorridos de ingestión
privada no afectados). Incluye universo, adaptador, localidad, constructor/IDs,
contexto/grafo y asignación espacial incierta con fixtures inventadas.
Seguridad estática: **178 controles aprobados**. La integridad comprobó sin
cambios las **244 entradas protegidas** del manifiesto previo y sus cuatro
resultados de revisión: **248 archivos**. No hubo entrenamiento, frontend/backend,
Docker, PostgreSQL ni push. Esta comprobación es local con GeoPandas/GeoParquet;
el recorrido PostGIS sigue pendiente y no se acredita por estos resultados.
