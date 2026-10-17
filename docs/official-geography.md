# Fase 3: diagnóstico geográfico privado

Esta fase asocia **registros de fuente**, todavía sin elegibilidad epidemiológica,
a candidatos censales. No genera conteos definitivos de casos, panel observado,
etiquetas, modelos ni ubicaciones públicas. Reutiliza la autorización y los
normalizados de [Fase 2](official-ingestion.md). Las fuentes no se editan.

## Ejecución local

Desde la raíz del repositorio, con los normalizados existentes:

```powershell
.\ml\venv\Scripts\python.exe -m sigard_ml.official.spatial_pipeline --config data/interim/official/access.private.json
```

Los parámetros se centralizan en `official/spatial_settings.py`. Para cambiarlos
sin editar código, usar `--spatial-config ml/configs/official.spatial.example.json`
o una copia **privada dentro de `data/interim/official/`** con referencias reales.
Nunca poner referencias de autorizaciones o información sanitaria en el ejemplo.
Los parámetros JSON reemplazan los valores predeterminados; se rechazan claves
desconocidas y distancias negativas o no finitas.

El manifiesto de Fase 2 se lee, sin modificarlo. El procedimiento exige usos de
inspección/procesamiento habilitados, hojas autorizadas y huellas de los Excel
coincidentes con el reporte de Fase 2. Lee únicamente sus Parquet normalizados.
Conserva la huella de cada normalizado consumido: Fase 2 no dejó una huella del
Parquet en su reporte, por lo que este control **no prueba retrospectivamente**
que un derivado no haya sido editado antes de Fase 3. El reporte de Fase 2 vincula
la entrega a los Excel; el manifiesto de Fase 3 fija la versión de los derivados
efectivamente analizados. No se relee ni renormaliza toda la entrega.

Ante errores, no se imprimen celdas ni mensajes de excepciones. La opción
`--diagnose-failure` muestra únicamente tipo de excepción y funciones/líneas.

## Módulos pequeños y responsabilidades

- `cartography.py`: lectura y controles del maestro censal; comparación con
  la fuente que ya utiliza `ingestion.territorial.load_cartography`.
- `spatial_assignment.py`: validación de puntos, coincidencias, distancias y
  clasificación de incertidumbre; no lee ni escribe archivos.
- `spatial_reports.py`: repeticiones, sondeos de límites, resumen seguro y
  explicación de viabilidad; no decide casos elegibles.
- `spatial_pipeline.py`: autorización, lectura de normalizados, coordinación,
  salidas privadas y comprobación de integridad.
- `spatial_settings.py`: versiones, rutas, tolerancia numérica y opciones.

## Cartografía y CRS

Se exige el maestro existente de 263 radios: IDs únicos de nueve dígitos con
prefijo `46014`, geometrías poligonales no nulas, no vacías y válidas. Se verifican
nombres territoriales cuando están presentes. La comparación con la fuente
censal original comprueba los mismos IDs y geometrías topológicamente iguales.
No se usa `make_valid`, simplificación, ajuste de límites ni reparación automática.

Las parejas de polígonos iguales se rechazan. Las intersecciones de área positiva
se reportan, aunque sean pequeñas; los puntos que coincidan con varias geometrías
quedan ambiguos. Compartir borde sin área positiva no es superposición. Se
informan componentes y huecos de la unión, sin presumir que un hueco es un error.
No hay un límite departamental independiente en esta auditoría: el territorio
se define como la unión de radios seleccionados por los códigos de Capital.
La igualdad con esa misma fuente no constituye una validación externa de límites.

EPSG:4326 se usa para intercambio y coincidencia topológica, con `x=longitud`,
`y=latitud`. Las distancias y áreas se calculan en EPSG:32719. Se diferencia
declarar un CRS de transformar mediante `to_crs`; no se corrigen ejes ni unidades.
El método sigue los predicados de [GeoPandas](https://geopandas.org/en/stable/docs/reference/api/geopandas.sjoin.html)
y la proyección [UTM de PROJ](https://proj.org/en/stable/operations/projections/utm.html).

**Capital cruza el borde oriental del área nominal de UTM 19S.** Se calcula el
factor de escala de Transversa Mercator en los extremos de su envolvente y en
los mínimos locales de distancia al meridiano central/latitud absoluta. Para
la cartografía vigente la desviación máxima resulta aproximadamente **0,101%**.
Esto permite conservar la convención métrica para diagnóstico local con esa
aproximación explícita: a 100 m, del orden de 0,11 m de diferencia de escala.
No se afirma que todo Capital esté dentro del área nominal de EPSG:32719.

`MAX_METRIC_SCALE_DEVIATION=0.002` fija una tolerancia numérica de **0,2%** para
este diagnóstico. Es una decisión de ingeniería editable, no una norma sanitaria
ni precisión del geocodificador. Si otra cartografía excede la tolerancia, se
detiene para revisar la proyección. Los puntos muy próximos a un umbral requieren
considerar esta aproximación. La comprobación no valida la superficie departamental
para trabajos geodésicos de precisión ni cambia los artefactos territoriales vigentes.

La configuración disponible todavía no confirma el CRS de los puntos. Se usa
la hipótesis explícita `assumed_crs=EPSG:4326` exclusivamente para diagnóstico.
Si se configura como `null`, no se calcula asignación territorial. Estar dentro
de Capital no confirma CRS, rol de residencia ni exactitud.

La función de asignación admite puntos proyectados **confirmados** EPSG:32719
y los transforma. La CLI rechaza esa declaración sobre los normalizados de
Fase 2, cuyo contrato almacena latitud/longitud candidatas en grados. Un futuro
contrato de fuentes proyectadas debe documentarse antes de incorporarlas.

## Contrato privado de asignación

Cada fila conserva `source_id`, `sheet_ref` y `record_ref`. Esa combinación es
la clave técnica, porque la referencia de Fase 2 no incorpora la hoja.
No se reescriben esas referencias ni se deduplican filas.

`coordinate_status` diferencia coordenadas utilizables bajo el CRS de trabajo,
faltantes, inválidas o de CRS desconocido. `geocoding_category` usa vocabulario
cerrado a partir de las etiquetas, sin copiarlas al reporte. Los originales
permanecen en los normalizados privados de Fase 2.

`geometry_status` conserva el resultado geométrico:

- `unique_interior`: un solo polígono cubre el punto y éste está en su interior.
- `boundary`: borde de un solo polígono; nunca se asigna automáticamente.
- `multiple_matches`: varias geometrías, incluidos bordes compartidos.
- `outside_territory`: ninguna coincidencia territorial.
- `missing_coordinates`, `invalid_coordinates`, `unknown_crs`: sin operación
  geométrica utilizables.

`assignment_state` expresa el resultado diagnóstico:

- `unique_geometry`: interior único, con evidencia configurada y sin señales
  pendientes. Tampoco certifica precisión epidemiológica.
- `uncertain`: interior único con candidato, pero con motivos de incertidumbre.
- `ambiguous`: borde o múltiples coincidencias; `radio_candidate` queda nulo.
- `unassigned`: coordenadas no utilizables o exterior; candidato nulo.

`matching_radios` conserva todas las coincidencias ordenadas. No se elige la
primera, no se usa vecino más cercano para exteriores y no se inventan posiciones
con centroides. `distance_to_boundary_m` es la distancia mínima a los límites
de **todos los radios**, incluidos límites interiores, sólo para puntos cubiertos.

`uncertainty_reasons` distingue CRS sin confirmar, exactitud y procedencia no
documentadas, etiqueta aproximada/desconocida, rol geográfico sin resolver,
posición compartida y proximidad a límites. Una repetición invita a revisar:
no significa necesariamente registro erróneo ni episodio duplicado.

`coordinate_group_ref` es opaco y determinista para la entrega, y
`coordinate_group_size` informa cuántas filas comparten el par numérico exacto.
No se redondean puntos ni se mezclan proximidad y repetición. Estos grupos
**no son identificadores de pacientes ni de episodios**. La comparación abarca
la entrega completa, a diferencia del control por hoja de Fase 2.

La columna `eligibility` conserva el estado previo cuando existe; por defecto
es `unresolved`, aunque la etiqueta original diga “Confirmado”. No se decide
elegibilidad, no se eliminan registros ni se asignan semanas epidemiológicas.
`epidemiological_precision_validated` permanece falso. Versión, CRS de trabajo,
condición real/ficticia y huella cartográfica se conservan en el Parquet; fuentes,
versiones y cobertura temporal preliminar se vinculan desde el JSON y manifiesto.
Es un diagnóstico de filas, distinto del contrato de episodio resuelto de Fase 1.

## Incertidumbre y escenarios

Por defecto **no hay margen de error documentado** ni umbral que clasifique
proximidad (`boundary_review_m=null`). Los radios alternativos no se deducen de
una etiqueta de calle o barrio sin extensión espacial conocida.

Los sondeos `sensitivity_distances_m=[10,25,50,100]` son escalas exploratorias
editables para conocer cuántas posiciones interiores están cerca de límites y
cuántas alcanzan más de un polígono. No son errores estimados ni probabilidades.
Se muestran tanto registros como coordenadas distintas, con cantidades pequeñas
suprimidas; no se divulgan las ubicaciones ni los radios de las concentraciones.

Si se define `boundary_review_m`, los candidatos alternativos quedan marcados
como `review_scenario`. Si existe un radio de incertidumbre fundamentado para
**toda la entrega**, puede fijarse `documented_uncertainty_m` con
`uncertainty_evidence_ref` obligatorio; los candidatos se etiquetan
`documented_radius`. Se seleccionan todos los polígonos cuya distancia al punto
no excede ese radio, sin probabilidades ni reasignación automática. La configuración
global no debe utilizarse si la evidencia sólo cubre una parte de la entrega:
en ese caso hace falta un contrato por método/fuente, todavía no implementado.

La procedencia y el significado geográfico se declaran mediante
`geocoding_provenance_ref` y `location_role`. Los encabezados de residencia
existentes son un indicio de intención, pero no demuestran qué ubicación devolvió
el geocodificador. Es necesario confirmar método, consultas, proveedor, CRS,
referencias territoriales y evaluación de error antes de justificar 263 radios
como resolución para un panel epidemiológico observado.

## Productos e integridad

Se escriben exclusivamente en `data/interim/official/geography/` por defecto:

- `assignments.parquet`: claves técnicas, grupos, candidatos, estados, motivos
  y elegibilidad. Sin nombres, documentos, domicilios, fechas individuales ni
  coordenadas exactas; la vinculación local con los normalizados es privada.
- `geographic_quality.json`: controles cartográficos, procedencia, período,
  estadísticas de calidad y sensibilidad. Sin desgloses epidemiológicos por radio.
- `territorial_viability.md`: explicación de límites y alternativas conceptuales.
- `integrity_manifest.json`: SHA-256 de entradas y artefactos científicos, y de
  las tres salidas anteriores, para auditoría local.

Se comprueban huellas de todas las fuentes/derivados en `data/`, artefactos en
`ml/artifacts/`, modelos en `ml/models/` y datos publicados de frontend antes
y después del proceso. Se permiten reejecuciones deterministas de estas salidas;
si la carpeta elegida contiene avances ajenos al procedimiento, se rechaza.
Se prohíben salidas públicas, `data/processed/official/`, la carpeta raíz de
Fase 2 y su subcarpeta `normalized/`. Las exclusiones de Git y Docker existentes
cubren estos resultados y cualquier configuración privada guardada junto a ellos.

La viabilidad de 263 radios queda **pendiente de evidencia de exactitud y de
reglas epidemiológicas**. Como alternativas sólo conceptuales se consideran
fracciones censales, conjuntos contiguos de radios o unidades administrativas
con límites oficiales. Agrupar no soluciona posiciones equivocadas ni sesgo de
geocodificación. No se implementa una agrupación territorial en esta fase.

## Pruebas

```powershell
.\ml\venv\Scripts\python.exe -m pytest ml/tests -p no:cacheprovider --basetemp=ml/.tmp/phase3-check
```

Usar una carpeta temporal nueva si hay conflictos de permisos previos. Las
pruebas geográficas utilizan exclusivamente polígonos, posiciones y libros Excel
ficticios. Incluyen todos los estados, proximidad métrica, CRS incorrecto y
transformación confirmada, geometrías inválidas, múltiples coincidencias,
reproducibilidad, conservación de fuentes y elegibilidad independiente.
El flujo completo prueba autorización, cambio de fuente, privacidad e integridad.
