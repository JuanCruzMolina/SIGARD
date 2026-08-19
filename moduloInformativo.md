# Planificación del módulo informativo y de participación ciudadana

> **Estado al 19/08/2026:** implementación técnica completada en el repositorio.
> La publicación como canal municipal oficial continúa bloqueada hasta confirmar
> un organismo receptor y sus condiciones operativas. La revisión visual,
> responsive y de accesibilidad asistida por navegador también queda pendiente
> porque el entorno de verificación no dispone de un navegador instalado.

## 0. Resultado implementado

- Ruta pública `/prevencion` con prevención, síntomas, signos de alarma,
  explicación de descacharreo/control vectorial y fuentes oficiales.
- Directorio versionado con 24 CAPS públicos y 3 hospitales de referencia,
  mapa, búsqueda, filtros, listado accesible, teléfonos y fechas de revisión.
- Contactos oficiales disponibles y aclaración explícita de que no se halló un
  celular municipal vigente dedicado exclusivamente a fumigación/descacharreo.
- Formulario anónimo con geolocalización opcional, marcador manual, validación
  territorial, privacidad, idempotencia y código de seguimiento.
- API y tabla `citizen_reports` independientes de datos, modelos y mapas
  epidemiológicos; migración Alembic con geometría PostGIS.
- Consulta pública limitada a estado y fechas, sin descripción ni ubicación.
- Ruta protegida `/admin/reportes` con filtros, detalle privado, estados,
  duplicados, notas, mensajes públicos, auditoría y exportación.
- Retención configurable (180 días por defecto), purga diaria incluida en Docker
  y límite antiabuso sin persistir la IP completa.
- Pruebas de alta, reintento idempotente, límites territoriales, rechazo de
  contacto directo, autenticación, actualización, privacidad pública y purga
  efectiva de reportes vencidos.

### Verificación ejecutada

- `npm run lint`: correcto.
- `npm run build`: compilación de producción correcta.
- `pytest -q`: **9 pruebas** de API e integración correctas.
- Migración Alembic compilada para PostgreSQL/PostGIS en modo offline.
- Contrato estático validado: 24 CAPS, 3 hospitales, 7 contactos, 7 fuentes,
  identificadores únicos y sin teléfonos enlazados únicamente a una portada
  genérica.
- De los 24 CAPS, **23 permanecen con `vigencia_por_confirmar`** y deben
  confirmarse institucionalmente antes de presentar el directorio como operativo
  en tiempo real. El CAPS Ciudad Nueva conserva el estado `publicado` según su
  fuente, que tampoco equivale a una verificación en vivo.
- No fue posible ejecutar revisión visual, responsive, navegación por teclado ni
  lector de pantalla asistidos por navegador porque no hay uno instalado en esta
  estación. Estas comprobaciones deben realizarse antes de publicar.

## 1. Propósito

Crear un nuevo módulo público de SIGARD orientado a la ciudadanía de la Ciudad
de La Rioja que permita:

- conocer cómo prevenir el dengue y evitar picaduras;
- reconocer síntomas y signos de alarma;
- ubicar los Centros de Atención Primaria de la Salud (CAPS) públicos;
- consultar hospitales públicos de referencia en una categoría separada;
- reportar de manera anónima posibles criaderos, acumulación de residuos u otros
  problemas que requieran evaluación, descacharreo o control vectorial;
- consultar el estado del reporte mediante un código de seguimiento.

El módulo se implementa como la ruta pública independiente `/prevencion`, para
no mezclar servicios ciudadanos con el mapa epidemiológico
experimental ni con resultados observados, sintéticos o predictivos.

## 2. Decisiones confirmadas

- Se mostrarán CAPS públicos de la Ciudad de La Rioja.
- Los hospitales públicos de referencia aparecerán en una categoría separada.
- Se utilizarán los registros oficiales y publicaciones disponibles, indicando
  siempre la fuente y fecha de revisión.
- El módulo tendrá un formulario propio dentro de SIGARD.
- Los reportes serán anónimos: no se solicitarán nombre, DNI, teléfono, correo ni
  una cuenta de usuario.
- La primera versión incluirá una bandeja administrativa protegida para revisar y
  gestionar reportes.
- La coordenada exacta de un reporte será privada y nunca se publicará en mapas,
  archivos o endpoints públicos.
- Los reportes ciudadanos no serán casos de dengue, evidencia epidemiológica ni
  features del modelo.

## 3. Alcance funcional

### 3.1 Incluido

- Contenido preventivo basado en fuentes sanitarias oficiales.
- Explicación clara de síntomas, signos de alarma y conducta recomendada.
- Explicación de la diferencia entre eliminación de criaderos, descacharreo y
  fumigación.
- Mapa interactivo y listado accesible de CAPS públicos.
- Categoría separada para hospitales públicos de referencia.
- Búsqueda y filtros por nombre, tipo de establecimiento y barrio.
- Acciones para llamar y abrir indicaciones de llegada.
- Formulario anónimo con selección de problema, descripción y ubicación.
- Código aleatorio para consultar el estado de un reporte.
- Bandeja administrativa para revisión, clasificación y actualización de estado.
- Procedencia, fecha de publicación y fecha de revisión de los datos sanitarios.

### 3.2 Fuera de alcance

- Diagnóstico médico o evaluación clínica dentro de SIGARD.
- Recolección de síntomas, enfermedades o antecedentes personales en el
  formulario ciudadano.
- Fotografías o archivos adjuntos en la primera versión.
- Publicación de reportes individuales o coordenadas exactas.
- Incorporación de los reportes al entrenamiento o evaluación del modelo.
- Presentación de un reporte como denuncia municipal formal mientras no exista un
  acuerdo o integración con el organismo competente.
- Promesa de fumigación, descacharreo, plazo de respuesta o intervención.
- Estado "abierto ahora" para establecimientos sin una fuente operativa en tiempo
  real.

## 4. Organización de la experiencia ciudadana

### 4.1 Acciones principales

El inicio del módulo debe ofrecer tres accesos claros:

1. **Prevenir en casa**.
2. **Buscar un centro de salud**.
3. **Reportar un problema**.

También debe mostrar una vía rápida hacia emergencias médicas cuando la persona
identifique signos de alarma.

### 4.2 Prevención en el hogar

La información debe presentarse como una lista breve y accionable:

- eliminar recipientes en desuso que puedan acumular agua;
- perforar, romper o compactar los objetos que no puedan reutilizarse;
- dar vuelta, cubrir o resguardar baldes, juguetes, tambores y otros recipientes;
- cepillar y renovar el agua de bebederos de animales;
- limpiar desagües, canaletas y colectores de aire acondicionado;
- tapar tanques, cisternas y otros depósitos;
- mantener patios y jardines desmalezados;
- mantener las piletas limpias, cloradas y cubiertas cuando no se utilicen;
- usar repelente siguiendo las indicaciones del envase;
- utilizar ropa clara que cubra brazos y piernas;
- colocar mosquiteros en puertas, ventanas, cunas y cochecitos.

La eliminación de criaderos debe aparecer como la medida preventiva principal y
como una tarea que debe sostenerse durante todo el año.

### 4.3 Síntomas y signos de alarma

El módulo debe diferenciar entre síntomas compatibles y situaciones que requieren
atención urgente.

Síntomas compatibles:

- fiebre de 38 °C o más;
- dolor de cabeza o detrás de los ojos;
- dolor muscular o articular;
- náuseas, vómitos o diarrea;
- malestar general;
- sarpullido.

Conducta recomendada:

- no automedicarse;
- no utilizar aspirina, ibuprofeno, ketorolac ni inyectables intramusculares ante
  una sospecha de dengue;
- concurrir al centro de salud más cercano.

Signos de alarma:

- dolor abdominal intenso;
- vómitos persistentes;
- sangrado de mucosas;
- irritabilidad, somnolencia o letargo;
- dificultad para respirar.

Ante estos signos se debe indicar atención urgente y destacar el número 107.

### 4.4 Descacharreo y fumigación

El módulo debe explicar que la fumigación:

- actúa principalmente sobre mosquitos adultos que entran en contacto con el
  insecticida durante la aplicación;
- no elimina por sí sola huevos, larvas ni pupas;
- no reemplaza la limpieza ni la eliminación de criaderos;
- corresponde a una decisión de la autoridad sanitaria ante brotes, focos o
  situaciones evaluadas técnicamente.

Por esta razón, el formulario no ofrecerá una promesa directa de "solicitar
fumigación". La opción se denominará **Solicitar evaluación para control
vectorial**, dejando que el equipo responsable determine la intervención
apropiada.

## 5. Directorio de CAPS y hospitales

### 5.1 Fuentes y condición operativa

El inventario inicial partirá de:

- los 24 CAPS de Capital mencionados por el Ministerio de Salud de La Rioja en
  marzo de 2024;
- el Registro Federal de Establecimientos de Salud (REFES) 2026;
- las fichas individuales publicadas por el Ministerio provincial;
- publicaciones sanitarias más recientes que mencionen servicios o vacunatorios
  activos.

La presencia de un establecimiento en REFES no demuestra por sí sola su horario o
funcionamiento diario. Como no existe un contacto institucional que confirme el
inventario, la interfaz mostrará:

- **Horario publicado**, en lugar de "abierto ahora";
- fecha de la fuente;
- fecha de última revisión en SIGARD;
- estado de verificación, por ejemplo `publicado`, `vigencia por confirmar` o
  `verificado institucionalmente`.

### 5.2 Hospitales de referencia iniciales

Se evaluarán como referencias públicas:

- Hospital Regional Enrique Vera Barros;
- Hospital de la Madre y el Niño;
- Hospital Escuela y de Clínicas Virgen María de Fátima.

Su función y tipo de atención deben describirse únicamente cuando exista una
fuente oficial que lo respalde.

### 5.3 Datos por establecimiento

Cada CAPS u hospital tendrá los siguientes campos:

```text
id
nombre
tipo: caps | hospital
domicilio
barrio
latitud
longitud
telefono
horario_publicado
servicios_relevantes
fuente_nombre
fuente_url
fecha_fuente
fecha_revision_sigard
estado_verificacion
```

### 5.4 Interacción del mapa

- Marcadores visualmente diferentes para CAPS y hospitales.
- Filtros por tipo y barrio.
- Búsqueda por nombre o domicilio.
- Panel de detalle al seleccionar un establecimiento.
- Botones **Llamar** y **Cómo llegar**.
- Listado textual equivalente al mapa para accesibilidad.
- Navegación completa mediante teclado.
- Comunicación que no dependa exclusivamente del color.

## 6. Formulario anónimo de reportes

### 6.1 Categorías

- Recipientes o agua acumulada.
- Neumáticos, chatarra u objetos voluminosos.
- Microbasural.
- Posible criadero en un espacio público.
- Alta presencia de mosquitos.
- Solicitud de evaluación para control vectorial.
- Otro problema relacionado.

### 6.2 Campos

Campos obligatorios:

- categoría;
- ubicación;
- descripción breve del problema;
- confirmación de lectura del aviso de privacidad y alcance del servicio.

El formulario no solicitará:

- nombre o apellido;
- DNI;
- teléfono;
- correo electrónico;
- usuario o contraseña;
- síntomas o datos de salud;
- información sobre otras personas.

### 6.3 Selección de ubicación

Se ofrecerán tres alternativas:

1. **Usar mi ubicación**, solicitando permiso explícito al navegador.
2. Colocar o mover un marcador manualmente.
3. Escribir una dirección o referencia.

La interfaz debe explicar que el permiso de geolocalización es opcional. La
persona podrá usar el marcador o la dirección manual si decide no compartir la
ubicación del dispositivo.

El backend validará que el punto se encuentre dentro del ámbito territorial
definido para la Ciudad de La Rioja. Los puntos fuera de esa cobertura mostrarán
un mensaje informativo y no se enviarán.

### 6.4 Confirmación y seguimiento

Después de un envío válido, SIGARD generará un código público aleatorio, por
ejemplo:

```text
SGD-RPT-7K4M2Q
```

El mensaje de confirmación debe aclarar:

> El reporte fue registrado de manera anónima en SIGARD para su revisión. Esto no
> significa que haya sido recibido por el Municipio ni garantiza una intervención.
> Guardá el código si querés consultar su estado.

La consulta pública por código sólo devolverá:

- estado general;
- fecha de recepción;
- fecha de última actualización;
- mensaje público del equipo revisor, si corresponde.

No devolverá descripción, dirección ni coordenadas.

## 7. Bandeja administrativa

La primera versión incluirá una ruta administrativa autenticada y autorizada por
rol.

Funciones mínimas:

- listado paginado de reportes;
- filtros por categoría, estado, fecha y barrio;
- visualización privada de ubicación y descripción;
- detección y marcado de posibles duplicados;
- cambio de estado;
- observación interna;
- mensaje público de seguimiento;
- exportación operativa controlada;
- registro de quién modificó cada reporte y cuándo.

Estados propuestos:

```text
recibido
en_revision
pendiente_de_derivacion
derivado
resuelto
descartado
```

Mientras no exista un receptor municipal confirmado, los reportes permanecerán en
`recibido`, `en_revision` o `pendiente_de_derivacion`. No se utilizará `derivado`
si el reporte no fue efectivamente remitido a un organismo.

## 8. Arquitectura técnica

### 8.1 Frontend

El frontend actual utiliza React, Vite, React Router y Leaflet. Se propone:

```text
frontend/src/pages/Prevencion.jsx
frontend/src/components/PreventionGuide.jsx
frontend/src/components/SymptomsAlert.jsx
frontend/src/components/HealthFacilitiesMap.jsx
frontend/src/components/CitizenReportForm.jsx
frontend/src/components/ReportConfirmation.jsx
frontend/src/services/preventionData.js
frontend/src/services/citizenReports.js
frontend/public/data/health_facilities.geojson
frontend/public/data/prevention_content.json
```

También se agregará la ruta `/prevencion` y su acceso en la navegación principal.

### 8.2 API implementada

Endpoints reales:

```text
GET   /
GET   /health
POST  /api/v1/citizen-reports
GET   /api/v1/citizen-reports/status/{tracking_code}
POST  /api/v1/geocoding/address
POST  /api/v1/admin/session
GET   /api/v1/admin/citizen-reports
GET   /api/v1/admin/citizen-reports/export.csv
GET   /api/v1/admin/citizen-reports/{id}
PATCH /api/v1/admin/citizen-reports/{id}
```

Los endpoints administrativos requerirán autenticación, autorización por rol y
auditoría.

### 8.3 Persistencia

Se creó una tabla independiente `citizen_reports`. No se reutilizan las tablas
`casos_dengue`, `alertas` ni `zonas_riesgo`.

Campos propuestos:

```text
id UUID PRIMARY KEY
tracking_code VARCHAR UNIQUE NOT NULL
category VARCHAR NOT NULL
description TEXT NOT NULL
latitude DOUBLE PRECISION NOT NULL
longitude DOUBLE PRECISION NOT NULL
geom GEOMETRY(Point, 4326) NOT NULL
address_reference VARCHAR NULL
neighborhood_id INTEGER NULL
status VARCHAR NOT NULL
public_status_message TEXT NULL
internal_notes TEXT NULL
privacy_notice_version VARCHAR NOT NULL
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
retention_until TIMESTAMPTZ NOT NULL
```

La estructura se aplica mediante una migración Alembic versionada, sin modificar
manualmente el volcado SQL existente.

## 9. Privacidad y seguridad

Aunque el reporte no contenga nombre o contacto, una coordenada exacta puede
revelar un domicilio. Por ello continuará tratándose como información privada.

Medidas mínimas:

- no almacenar identificadores directos de la persona;
- no requerir autenticación ciudadana;
- solicitar permiso de geolocalización sólo después de una acción explícita;
- no almacenar la IP completa, salvo que una evaluación de seguridad documentada
  determine que sea indispensable;
- si se requiere control de abuso, preferir un identificador técnico temporal o
  hash rotativo con vencimiento corto;
- cifrado en tránsito mediante HTTPS;
- acceso a ubicación exacta restringido a administradores autorizados;
- validación de longitud, formato, categoría y límites territoriales;
- protección contra spam, automatización y envíos masivos;
- auditoría de cambios administrativos;
- política de retención y eliminación;
- prohibición de enviar coordenadas exactas a herramientas analíticas de terceros;
- prohibición de publicar reportes individuales.

La implementación configura una retención inicial de 180 días para ubicación y
descripción exactas. `python -m app.retention` elimina los reportes vencidos. El
servicio `retention` de Docker ejecuta esa purga al iniciar y luego cada 24 horas;
fuera de Docker se requiere una tarea diaria equivalente.
Este plazo deberá validarse antes de producción con el responsable institucional y
la política de privacidad del sistema.

## 10. Separación epidemiológica

Los reportes ciudadanos representan solicitudes operativas y percepciones de la
comunidad. No equivalen a:

- casos sospechosos;
- casos confirmados;
- observaciones epidemiológicas;
- asignaciones sintéticas por radio;
- predicciones del modelo;
- evidencia de riesgo territorial.

Por lo tanto:

- no se incorporarán al panel `radio censal - semana epidemiológica`;
- no se usarán como variable objetivo ni feature;
- no aparecerán sobre el mapa epidemiológico público;
- no se utilizarán para afirmar presencia o circulación de dengue;
- cualquier estadística futura de reportes se mostrará como actividad ciudadana,
  con agregación espacial y temporal suficiente.

## 11. Contactos iniciales

Contactos respaldados por sitios o publicaciones oficiales:

- Emergencias médicas: `107`.
- Emergencias generales: `911`.
- Ministerio de Salud de La Rioja: `(0380) 445-3700`.
- COE provincial: `0800-444-0353`, sujeto a revisión de horario y vigencia.
- Municipalidad de La Rioja: `4470000`, `4427375` y `4740901`.

El WhatsApp `380 444-5300` aparece en publicaciones anteriores como Centro de
Atención al Vecino, pero no está confirmado actualmente en el sitio oficial. Debe
permanecer marcado como `pendiente_de_verificacion` y no publicarse como vigente
hasta contar con una fuente actualizada.

## 12. Fases de implementación

Las cinco fases técnicas se completaron. La lista siguiente se conserva como
trazabilidad del plan original. La fase 5 queda parcialmente condicionada por la
revisión visual y de accesibilidad en un entorno con navegador.

### Fase 1. Consolidación de información — 1 a 2 días

- Normalizar CAPS y hospitales.
- Obtener y revisar coordenadas.
- Registrar fuente y fecha de cada dato.
- Redactar el contenido preventivo.
- Preparar el contrato de datos del directorio.

### Fase 2. Página informativa y mapa — 2 a 3 días

- Crear la ruta y navegación.
- Implementar prevención, síntomas y explicación de control vectorial.
- Implementar mapa, filtros, búsqueda y listado accesible.
- Adaptar la interfaz a dispositivos móviles.

### Fase 3. Formulario, API y persistencia — 2 a 3 días

- Implementar el formulario anónimo.
- Incorporar selección manual y geolocalización opcional.
- Validar límites territoriales.
- Crear endpoints y migración de base de datos.
- Generar códigos de seguimiento.
- Implementar consulta pública de estado.

### Fase 4. Bandeja administrativa — 2 días

- Implementar autenticación y autorización.
- Crear listado, filtros y detalle.
- Permitir cambios de estado y mensajes públicos.
- Incorporar auditoría y exportación controlada.

### Fase 5. Verificación — 1 a 2 días

- Pruebas unitarias y de integración.
- Pruebas de envío duplicado y errores de red.
- Revisión de seguridad y privacidad.
- Comprobación de que las coordenadas no lleguen a rutas públicas.
- Revisión de accesibilidad con teclado y lector de pantalla.
- Verificación visual en escritorio y dispositivos móviles.

Estimación total: **8 a 12 días hábiles** para una primera versión completa.

## 13. Criterios de aceptación

- Todos los establecimientos cargados aparecen en el mapa y el listado.
- CAPS y hospitales se distinguen sin depender sólo del color.
- Cada establecimiento muestra fuente y fecha de revisión.
- Ningún establecimiento afirma estar abierto en tiempo real sin una fuente que lo
  confirme.
- El formulario no solicita identificadores directos ni datos de salud.
- La geolocalización del dispositivo es opcional.
- El backend rechaza ubicaciones fuera del alcance territorial.
- Un envío válido devuelve un código de seguimiento no predecible.
- Los reintentos de red no generan reportes duplicados.
- La consulta pública por código no revela descripción, dirección ni coordenadas.
- Las coordenadas exactas sólo están disponibles para personal autorizado.
- Existe trazabilidad de los cambios administrativos.
- La interfaz no promete fumigación ni intervención municipal.
- Los reportes no se mezclan con datos observados, sintéticos o predictivos.
- La experiencia funciona con teclado y en pantallas móviles.
- Los textos sanitarios enlazan a fuentes oficiales.

## 14. Fuentes iniciales

- [Cómo prevenir el dengue — Ministerio de Salud de la Nación](https://www.argentina.gob.ar/como-prevenir-el-dengue)
- [Cómo evitar picaduras de mosquitos — Ministerio de Salud de la Nación](https://www.argentina.gob.ar/como-evitar-picaduras-de-mosquitos)
- [Síntomas y signos de alarma — Ministerio de Salud de la Nación](https://www.argentina.gob.ar/sintomas-y-signos-de-alarma)
- [Información nacional sobre fumigación y eliminación de criaderos](https://www.argentina.gob.ar/node/371159)
- [Atención por dengue en Capital — Ministerio de Salud de La Rioja](https://salud.larioja.gob.ar/index.php?Itemid=170&catid=8&id=1387%3Ainforman-lugares-horarios-y-telefonos-de-contacto-de-atencion-por-consultas-sobre-dengue&option=com_content&view=article)
- [Registro Federal de Establecimientos de Salud](https://datos.salud.gob.ar/dataset/listado-establecimientos-de-salud-asentados-en-el-registro-federal-refes)
- [Municipalidad de La Rioja](https://www.municipiolarioja.gob.ar/)
- [Ley 25.326 de Protección de los Datos Personales](https://www.argentina.gob.ar/normativa/nacional/ley-25326-64790/texto)

## 15. Dependencia operativa pendiente

Antes de presentar el formulario como un canal oficial de solicitud será necesario
obtener:

- un organismo receptor;
- una persona o área responsable;
- un medio de derivación confirmado;
- categorías y prioridades acordadas;
- plazos de conservación y respuesta;
- autorización para utilizar los nombres y contactos institucionales.

Hasta entonces, SIGARD debe describir el formulario como un **registro ciudadano
para revisión interna**, sin afirmar que reemplaza los canales municipales.
