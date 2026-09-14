# Plan técnico del proyecto SIGARD

**Proyecto:** Sistema informático para la geolocalización y alerta de zonas de riesgo por dengue en La Rioja Capital  
**Versión del plan:** 0.1  
**Fecha de elaboración:** 14 de septiembre de 2026  
**Horizonte:** 16 semanas  
**Equipo base estimado:** 2 integrantes  
**Audiencia principal:** equipo técnico  
**Estado:** línea base de ejecución sujeta a validación institucional

## 1. Propósito

Este documento organiza la ejecución técnica de SIGARD en doce etapas
secuenciales. Parte de los requerimientos preliminares y del estado observable
del repositorio; por lo tanto, distingue el trabajo ya avanzado de las brechas
que todavía deben resolverse.

El plan corresponde a un prototipo académico. Su objetivo es validar un flujo
técnico reproducible de preparación de datos, evaluación predictiva,
persistencia, publicación y visualización. No constituye un despliegue
productivo del Ministerio de Salud ni acredita capacidad epidemiológica real
para localizar casos por radio censal.

## 2. Fuentes y documentos relacionados

La planificación se basa en:

- `SIGARD_Requerimientos_LineaBase_v0.1.md`;
- `Relevamiento_requerimientos_md.md`;
- [Arquitectura conceptual](architecture.md);
- [Contrato conceptual de datos](data-contract.md);
- [Metodología](methodology.md);
- [Funcionalidades del MVP](mvp-funcionalidades.md);
- [Política de datos](../data/README.md).

Los dos primeros documentos constituyen un relevamiento documental preliminar.
No prueban que los requisitos hayan sido validados mediante entrevistas o por
referentes del Ministerio de Salud.

## 3. Principios obligatorios

1. La unidad experimental de `v0.1` es `radio censal - semana epidemiológica`.
2. Deben permanecer separados:
   - los casos observados agregados de Capital;
   - las asignaciones sintéticas por radio;
   - las predicciones producidas por los modelos.
3. Las asignaciones y coordenadas sintéticas no representan ubicaciones reales
   ni constituyen evidencia epidemiológica.
4. Las coordenadas sintéticas no pueden utilizarse como features, targets
   observados ni evidencia de domicilios.
5. El entrenamiento y la evaluación se ejecutan fuera del backend. La API sólo
   consume y publica artefactos ya generados y versionados.
6. `data/raw/` es inmutable. Las salidas parciales se escriben en
   `data/interim/` y los productos listos para consumo en `data/processed/`.
7. Toda generación aleatoria debe usar semillas explícitas y deterministas.
8. La evaluación debe utilizar cortes temporales; no se permiten particiones
   aleatorias de filas ni features que incorporen información futura.
9. La capa pública sólo recibe productos agregados o disociados. Nunca debe
   descargar casos detallados para ocultarlos posteriormente en el frontend.
10. El acceso ciudadano es público y anónimo. Las funciones administrativas
    requieren autenticación, autorización y auditoría.
11. Una alerta algorítmica es una candidata: nunca se publica automáticamente.
12. Los reportes ciudadanos son un dominio operativo separado y no alimentan
    el modelo, el panel radio-semana ni el mapa epidemiológico.

## 4. Estado inicial del repositorio

La clasificación utilizada en las etapas es:

- **Avanzado:** existe una implementación sustancial, aunque falten integración
  o evidencias de cierre.
- **Parcial:** existe una base reutilizable, pero no satisface aún todo el
  alcance de la etapa.
- **Pendiente:** no se identificó una implementación equivalente al requisito.

Al elaborar este plan se observó lo siguiente:

- Git y `docker-compose.yml` ya están presentes.
- Docker define `db`, `backend`, `retention` y `frontend`, pero el arranque
  requiere crear `backend/.env` y sustituir secretos de ejemplo.
- PostgreSQL/PostGIS y Alembic existen, aunque el esquema operativo actual se
  concentra en reportes ciudadanos y usuarios.
- FastAPI expone salud, geocodificación y reportes ciudadanos públicos y
  administrativos; todavía no sirve el contrato epidemiológico completo.
- La ingestión, preparación territorial, simulación, features, baselines y
  variantes Random Forest poseen implementaciones y pruebas específicas.
- El frontend React/Leaflet consume principalmente artefactos estáticos
  versionados.
- El módulo público de prevención y reportes ciudadanos está avanzado, pero no
  existe gestión editorial completa del contenido sanitario.
- No se identificó un flujo completo de alertas epidemiológicas candidatas,
  aprobación y publicación.

Este diagnóstico es una fotografía del repositorio, no una certificación de
que todas las suites o ambientes estén aprobados.

## 5. Cronograma general

| Etapa | Semanas | Duración | Estado inicial |
| --- | --- | ---: | --- |
| 0. Bootstrap Docker + Git | 1 | 1 semana | Parcial |
| 1. Arquitectura y configuración base | 2 | 1 semana | Parcial |
| 2. Persistencia PostgreSQL/PostGIS | 3-4 | 2 semanas | Parcial |
| 3. Backend mínimo | 5 | 1 semana | Parcial |
| 4. Ingestión de datos | 6-7 | 2 semanas | Avanzado |
| 5. Autenticación y autorización administrativa | 8 | 1 semana | Parcial |
| 6. API pública con información agregada | 9 | 1 semana | Pendiente |
| 7. Visualización geográfica | 10-11 | 2 semanas | Avanzado |
| 8. Componente predictivo | 12-13 | 2 semanas | Avanzado y exploratorio |
| 9. Alertas con validación administrativa | 14 | 1 semana | Pendiente |
| 10. Información sanitaria | 15 | 1 semana | Parcial |
| 11. Pruebas, seguridad y validación | 16 | 1 semana | Parcial |

La suma de las etapas es de 16 semanas. Aunque documentación, seguridad y
pruebas se trabajan desde el comienzo, su consolidación y aceptación integral
se realiza en la etapa 11.

---

## 6. Etapas de ejecución

### 0. Bootstrap Docker + Git

**Período:** semana 1  
**Estado inicial:** parcial

#### Objetivo

Disponer de un repositorio reproducible y de un entorno local que permita
levantar los servicios básicos sin versionar datos, modelos ni secretos.

#### Actividades

- Confirmar `main` como rama estable y utilizar ramas de trabajo breves con
  revisión antes de integrar.
- Documentar convenciones de commits, pull requests, versionado y etiquetas.
- Revisar `.gitignore` para excluir `.env`, fuentes, derivados, artefactos de
  modelos, entornos virtuales y dependencias instaladas.
- Crear los archivos locales `.env` desde los ejemplos y reemplazar claves,
  contraseñas y credenciales de bootstrap.
- Eliminar del Compose las credenciales operativas fijas o sustituirlas por
  variables requeridas desde el entorno.
- Validar construcción, dependencias y healthchecks de `db`, `backend`,
  `retention` y `frontend`.
- Documentar comandos de arranque, detención, migración y diagnóstico.

#### Entregables

- Convenciones de Git y flujo de integración documentados.
- `.env.example` completos, sin secretos válidos.
- Compose validado y procedimiento de bootstrap reproducible.
- Lista inicial de comprobaciones de salud.

#### Dependencias

No posee dependencias internas. Requiere Docker, Git y acceso a las
dependencias declaradas por cada componente.

#### Requisitos relacionados

RNF-05, RNF-11, RNF-12, RNF-13 y RNF-14.

#### Criterio de finalización

Desde un clon limpio, dos integrantes pueden configurar el entorno sin copiar
secretos al repositorio; `docker compose config` resulta válido y los cuatro
servicios alcanzan el estado esperado según el procedimiento documentado.

---

### 1. Arquitectura y configuración base

**Período:** semana 2  
**Estado inicial:** parcial

#### Objetivo

Consolidar una arquitectura lógica coherente con el código y establecer los
contratos que guiarán persistencia, API, frontend y procesamiento offline.

#### Actividades

- Actualizar el estado declarado en la documentación para que no describa como
  futuro aquello que ya está implementado.
- Mantener separados preparación/ML, persistencia, API y visualización.
- Definir los límites entre API pública, API administrativa y procesos offline.
- Formalizar el contrato de procedencia y las categorías `observado`,
  `sintético` y `predicho`.
- Definir configuración por ambiente, gestión de logs y política de errores.
- Mantener el frontend desplegable en Vercel sin asumir que FastAPI o PostGIS
  se ejecutarán allí.
- Elaborar un modelo de amenazas inicial y vincular controles con RNF.

#### Entregables

- Arquitectura conceptual actualizada.
- Contratos de datos y servicios versionados.
- Diagrama de despliegue por ambiente.
- Registro inicial de decisiones arquitectónicas y amenazas.

#### Dependencias

Bootstrap Docker + Git completado.

#### Requisitos relacionados

RF-01 a RF-20; RNF-01 a RNF-14; RN-01 a RN-12.

#### Criterio de finalización

La documentación representa el comportamiento del repositorio y permite
determinar, para cada dato o proceso, qué componente lo produce, almacena,
publica y valida.

---

### 2. Persistencia PostgreSQL/PostGIS

**Período:** semanas 3 y 4  
**Estado inicial:** parcial

#### Objetivo

Representar en PostgreSQL/PostGIS el contrato epidemiológico y territorial sin
mezclarlo con el dominio de reportes ciudadanos.

#### Actividades

- Conservar `usuarios`, `citizen_reports` y su auditoría como dominio operativo
  independiente.
- Crear mediante Alembic entidades para:
  - radios censales y geometrías oficiales;
  - observaciones agregadas de Capital por semana epidemiológica;
  - clima histórico semanal;
  - asignaciones sintéticas por radio-semana;
  - predicciones y versiones de modelo/datos;
  - alertas, condiciones, estados e historial de aprobación;
  - contenido sanitario, fuente, revisión y vigencia;
  - auditoría administrativa transversal.
- Registrar procedencia, período, unidad, versión de transformación y condición
  real, sintética o predicha.
- Agregar claves únicas, restricciones de no negatividad, relaciones, índices
  temporales e índices espaciales GiST.
- Definir vistas o consultas específicas para productos públicos agregados.
- Documentar backup, restauración, retención y eliminación.

#### Entregables

- Migraciones Alembic incrementales y reversibles.
- Modelo físico documentado.
- Carga mínima de datos de prueba no sensibles.
- Consultas de integridad y geoespaciales verificables.

#### Dependencias

Contratos de arquitectura y datos aprobados.

#### Requisitos relacionados

RF-01 a RF-05, RF-08 a RF-14, RF-17 y RF-20; RNF-01, RNF-04, RNF-06,
RNF-07, RNF-08, RNF-11 y RNF-12.

#### Criterio de finalización

Una base vacía puede migrarse hasta la última versión, recibir fixtures no
sensibles y responder consultas temporales y PostGIS. Las restricciones impiden
sobrescribir o confundir observaciones, asignaciones sintéticas y predicciones.

---

### 3. Backend mínimo

**Período:** semana 5  
**Estado inicial:** parcial

#### Objetivo

Establecer una API FastAPI mínima y modular que sirva información persistida,
sin ejecutar preparación ni entrenamiento durante solicitudes HTTP.

#### Actividades

- Mantener `GET /health` y los endpoints existentes de reportes ciudadanos.
- Separar routers públicos, administrativos y operativos bajo `/api/v1`.
- Incorporar sesiones de base de datos, esquemas de entrada/salida y servicios
  para los nuevos dominios.
- Unificar validación, errores, paginación, ordenamiento y límites de consulta.
- Agregar metadatos de versión y advertencias metodológicas en las respuestas
  epidemiológicas.
- Mantener deshabilitado cualquier entrenamiento, simulación o generación de
  coordenadas dentro del proceso web.
- Generar y revisar OpenAPI como contrato verificable.

#### Entregables

- Estructura modular de FastAPI.
- OpenAPI actualizado.
- Acceso a PostGIS mediante servicios separados de los routers.
- Pruebas mínimas de salud, errores y conexión.

#### Dependencias

Persistencia migrada y contrato de API definido.

#### Requisitos relacionados

RF-09 a RF-20; RNF-02, RNF-03, RNF-06, RNF-09 y RNF-14.

#### Criterio de finalización

La API inicia sobre una base migrada, expone OpenAPI sin errores, responde el
healthcheck y no ejecuta entrenamiento ni generación sintética ante peticiones.

---

### 4. Ingestión de datos

**Período:** semanas 6 y 7  
**Estado inicial:** avanzado

#### Objetivo

Integrar los pipelines existentes con la persistencia y garantizar productos
deterministas, trazables y aptos para modelado y publicación.

#### Actividades

- Reutilizar la ingestión territorial, temporal y climática existente.
- Validar calendarios epidemiológicos sin asumir 52 semanas por año.
- Mantener diferencias entre cero explícito, registro ausente y período fuera
  de cobertura.
- Conservar la suma semanal exacta entre total observado de Capital y
  asignaciones sintéticas por radio.
- Validar que el universo territorial contenga los 263 radios esperados antes
  de publicar productos del MVP.
- Cargar productos procesados en PostGIS mediante una tarea offline idempotente.
- Guardar procedencia, hashes o versiones, cobertura, reglas de calidad y
  semillas.
- Evitar que la carga reemplace fuentes o productos existentes sin una opción
  explícita y acotada.

#### Entregables

- Datasets normalizados y reportes de calidad reproducibles.
- Cargador offline hacia PostGIS.
- Registro de ejecuciones y procedencia.
- Pruebas de conservación, unicidad, cobertura y determinismo.

#### Dependencias

Persistencia disponible y fuentes autorizadas o datasets sintéticos claramente
identificados.

#### Requisitos relacionados

RF-01 a RF-05; RN-07; CA-01 y CA-04.

#### Criterio de finalización

Una ejecución repetida con las mismas fuentes, configuraciones y semillas
produce resultados equivalentes, conserva los totales semanales y genera un
reporte que distingue cero observado, ausencia y datos sintéticos.

---

### 5. Autenticación y autorización administrativa

**Período:** semana 8  
**Estado inicial:** parcial

#### Objetivo

Extender la autenticación administrativa existente a todos los recursos
restringidos y garantizar trazabilidad de las operaciones sensibles.

#### Actividades

- Reutilizar JWT, contraseñas hasheadas y rol `admin` existentes.
- Aplicar autorización a datos epidemiológicos restringidos, alertas, contenido
  sanitario y exportaciones.
- Definir alta, desactivación, recuperación y rotación de credenciales.
- Retirar la contraseña de bootstrap una vez creada la primera cuenta.
- Registrar lecturas sensibles, cambios de estado, exportaciones y edición de
  contenido.
- Incluir respuestas `401` para falta de autenticación y `403` para rol
  insuficiente.
- Mantener todas las funciones ciudadanas básicas sin registro.

#### Entregables

- Dependencias de autorización reutilizables.
- Flujo documentado de cuentas administrativas.
- Auditoría ampliada.
- Pruebas positivas y negativas de acceso.

#### Dependencias

Backend modular y entidades administrativas migradas.

#### Requisitos relacionados

RF-15 a RF-18; RNF-02, RNF-03, RNF-05, RNF-06 y RNF-11; RN-01, RN-02 y
RN-05.

#### Criterio de finalización

Los endpoints restringidos rechazan correctamente solicitudes anónimas o sin
rol, las contraseñas no se almacenan en texto plano y toda operación sensible
definida genera un registro de auditoría.

---

### 6. API pública con información agregada

**Período:** semana 9  
**Estado inicial:** pendiente

#### Objetivo

Publicar el contrato epidemiológico y sanitario permitido sin exponer registros
individuales, reportes privados ni datos administrativos.

#### Interfaces previstas

```text
GET /api/v1/public/weeks
GET /api/v1/public/predictions/{week}
GET /api/v1/public/territorial-context
GET /api/v1/public/experimental-spatial-history/{week}
GET /api/v1/public/alerts
GET /api/v1/public/health-content
```

#### Actividades

- Publicar semanas disponibles como única fuente del selector temporal.
- Servir la predicción temporal agregada de Capital con versión y corte.
- Servir contexto territorial real sin convertirlo en riesgo epidemiológico.
- Servir la simulación espacial experimental como producto sintético separado.
- Entregar únicamente alertas aprobadas y publicadas.
- Incorporar advertencias, fuente, fecha de revisión y versión de esquema.
- Implementar cache control, validación de parámetros y límites de tamaño.
- Probar payloads para confirmar la ausencia de coordenadas individuales,
  descripciones privadas, notas, credenciales e identificadores internos.

#### Entregables

- Routers y esquemas públicos.
- Contrato OpenAPI actualizado.
- Pruebas de privacidad de respuestas.
- Estrategia documentada de caché y versionado.

#### Dependencias

Ingestión cargada, backend mínimo operativo y reglas de publicación aprobadas.

#### Requisitos relacionados

RF-09, RF-11, RF-14, RF-18 y RF-19; RNF-01, RNF-08 y RNF-09; RN-01,
RN-03, RN-04 y RN-11.

#### Criterio de finalización

Las interfaces públicas responden sin autenticación, mantienen alineación
temporal y no incluyen información individualizable ni productos sin el estado
de publicación correspondiente.

---

### 7. Visualización geográfica

**Período:** semanas 10 y 11  
**Estado inicial:** avanzado

#### Objetivo

Consolidar una interfaz cartográfica accesible que distinga con claridad
contexto territorial, simulación sintética y predicción temporal.

#### Actividades

- Migrar progresivamente desde archivos estáticos hacia la API pública.
- Mantener los artefactos estáticos sólo como fallback de demostración
  versionado durante la transición.
- Validar coincidencia exacta de corte, inicio y fin de semana objetivo.
- Verificar 263 radios antes de renderizar una capa territorial.
- Mostrar leyendas, unidades, fuentes, fecha de corte y advertencias.
- No denominar `riesgo epidemiológico` al contexto censal o a un percentil
  sintético.
- Implementar estados de carga, error, datos incompatibles y fuente no
  disponible.
- Completar comportamiento responsive, navegación por teclado, foco visible,
  contraste, alternativas textuales y lector de pantalla.

#### Entregables

- Dashboard y mapa integrados con la API.
- Componentes de leyenda y advertencias reutilizables.
- Fallback estático documentado.
- Evidencias de accesibilidad y responsive.

#### Dependencias

API pública agregada y contratos temporales/territoriales estables.

#### Requisitos relacionados

RF-09 a RF-11, RF-18 y RF-19; RNF-01, RNF-08, RNF-09, RNF-10 y RNF-14.

#### Criterio de finalización

El selector actualiza coherentemente predicción y capa experimental, cada capa
territorial posee 263 radios, los datos sintéticos están rotulados y ninguna
vista afirma precisión espacial real.

---

### 8. Componente predictivo

**Período:** semanas 12 y 13  
**Estado inicial:** avanzado y exploratorio

#### Objetivo

Consolidar la evaluación reproducible de los componentes predictivos sin
atribuir validez espacial real a targets sintéticos.

#### Actividades

- Mantener el entrenamiento y la evaluación como pipelines offline.
- Ejecutar baselines temporales antes de interpretar el Random Forest.
- Usar cortes temporales expansivos y un holdout final no utilizado para
  selección.
- Ajustar transformaciones únicamente con el conjunto de entrenamiento.
- Crear features sólo con información disponible hasta la semana de emisión.
- Documentar por separado:
  - la predicción temporal agregada de casos de Capital para la semana
    siguiente;
  - el experimento radio-semana cuyo target espacial es sintético;
  - la simulación espacial utilizada para demostrar el flujo visual.
- Versionar configuraciones, métricas, datos de entrada y fecha lógica de
  emisión sin versionar modelos entrenados.
- Publicar advertencias metodológicas junto con los artefactos de presentación.

#### Entregables

- Baseline y modelos candidatos reproducibles.
- Backtest temporal y comparación de métricas.
- Artefactos de publicación versionados.
- Informe de limitaciones y procedencia.

#### Dependencias

Pipeline de datos validado y contrato radio-semana estable.

#### Requisitos relacionados

RF-06 a RF-08 y RF-11; CA-06 y CA-07.

#### Criterio de finalización

La ejecución reproduce el backtest y la comparación con el baseline sin fuga
temporal. Los informes separan el desempeño temporal departamental del
experimento espacial sintético y no presentan este último como validación
epidemiológica.

---

### 9. Alertas con validación administrativa

**Período:** semana 14  
**Estado inicial:** pendiente

#### Objetivo

Implementar alertas epidemiológicas controladas en las que una condición
algorítmica nunca produzca por sí sola una comunicación pública.

#### Estados mínimos

```text
candidata -> aprobada -> publicada
         \-> rechazada
```

Una alerta rechazada no puede publicarse. Una alerta publicada conserva la
identidad del administrador aprobador, fechas, condición de origen y versión
del resultado que la generó.

#### Actividades

- Definir condiciones por zona y umbral, registrando su responsable y versión.
- Generar alertas candidatas a partir de resultados ya persistidos.
- Implementar bandeja administrativa, detalle, aprobación y rechazo.
- Requerir una acción explícita para publicar una alerta aprobada.
- Exponer públicamente sólo alertas en estado `publicada`.
- Auditar toda transición y evitar modificaciones destructivas del historial.
- Mantener las alertas epidemiológicas separadas de `citizen_reports`.

#### Entregables

- Entidades, migraciones y máquina de estados.
- Servicios y endpoints administrativos.
- Endpoint público filtrado.
- Interfaz administrativa y pruebas de transición.

#### Dependencias

Autorización administrativa, resultados persistidos y reglas institucionales
de publicación definidas.

#### Requisitos relacionados

RF-12 a RF-14; RN-06; CA-08.

#### Criterio de finalización

Ninguna alerta candidata o rechazada puede recuperarse desde la API pública.
Toda alerta publicada posee aprobación identificable y un historial de estados
auditable.

---

### 10. Información sanitaria

**Período:** semana 15  
**Estado inicial:** parcial

#### Objetivo

Completar la consulta pública y la gestión administrativa del contenido
sanitario, preservando fuente, revisión y vigencia.

#### Actividades

- Conservar recomendaciones, síntomas, signos de alarma y conducta recomendada
  provenientes de organismos oficiales.
- Mantener el directorio público de CAPS y hospitales con fuente, fecha de
  revisión, precisión y estado de verificación.
- No presentar `vigencia_por_confirmar` como disponibilidad operativa actual.
- Incorporar edición administrativa con borrador o publicación controlada.
- Registrar autor, fuente, fecha de revisión, versión y cambios auditables.
- Mantener la geocodificación y los reportes ciudadanos como flujos separados
  del contenido y del mapa epidemiológico.

#### Entregables

- Modelo y migración de contenido sanitario.
- API pública de lectura y API administrativa de gestión.
- Interfaz editorial protegida.
- Política de revisión y vigencia.

#### Dependencias

Autenticación administrativa, API pública y responsable editorial definido.

#### Requisitos relacionados

RF-19 y RF-20; RN-11; CA-12.

#### Criterio de finalización

Una persona sin autenticación puede consultar únicamente contenido publicado;
un administrador puede modificarlo con auditoría y cada publicación conserva
fuente, revisión y estado de vigencia.

---

### 11. Pruebas, seguridad y validación

**Período:** semana 16  
**Estado inicial:** parcial

#### Objetivo

Consolidar evidencia verificable del funcionamiento, la seguridad, la
privacidad, el rendimiento, la usabilidad y las limitaciones del prototipo.

#### Actividades

- Ejecutar desde un entorno limpio pruebas unitarias, integración, migraciones,
  contratos y recorridos extremo a extremo.
- Verificar respuestas `401`, `403`, `404`, `409` y `422` en los escenarios
  correspondientes.
- Inspeccionar la API pública para detectar datos individualizables.
- Revisar cifrado en tránsito y reposo, secretos, CORS, headers, JWT, RBAC,
  auditoría y logs.
- Probar retención, eliminación y restauración sobre datos de prueba.
- Medir la consulta cartográfica con operación, volumen, concurrencia,
  infraestructura y percentil documentados.
- Ejecutar pruebas responsive, teclado, foco, lector de pantalla y usabilidad.
- Validar determinismo de pipelines, conservación de totales y cortes
  temporales sin fuga.
- Preparar una matriz `RF/RNF -> caso de prueba -> evidencia -> resultado`.
- Realizar la aceptación externa sólo con referentes e instrumento identificados.

#### Entregables

- Informe de pruebas funcionales y de integración.
- Informe de seguridad y privacidad.
- Evidencia de backup/restauración y retención.
- Informe de rendimiento y usabilidad.
- Matriz de trazabilidad y acta de aceptación o pendientes.

#### Dependencias

Todas las etapas anteriores integradas en un ambiente de prueba reproducible.

#### Requisitos relacionados

Todos los RF, RNF, reglas de negocio y criterios CA-01 a CA-13 de la línea base.

#### Criterio de finalización

La suite completa puede ejecutarse desde un entorno limpio, cada requisito en
alcance posee evidencia y las limitaciones o incumplimientos remanentes están
registrados sin presentarse como funcionalidades validadas.

## 7. Dependencias críticas y puertas de decisión

### G0. Autorización y disponibilidad de datos

Antes de utilizar datos sensibles reales deben existir autorización,
responsable, finalidad, alcance, almacenamiento, retención, eliminación y
resultados publicables. Si esta puerta no se cumple, el desarrollo continúa sólo
con datos públicos, agregados o sintéticos identificados.

### G1. Granularidad territorial

La precisión efectiva debe auditarse antes de afirmar capacidad por radio. Si
los registros oficiales sólo están agregados para Capital, la salida espacial
se mantiene experimental y sintética.

### G2. Reglas de publicación

Antes de habilitar la API pública deben estar definidos los umbrales de
supresión o generalización, el contenido permitido y las pruebas de
reidentificación.

### G3. Alertas y responsables

Antes de generar comunicaciones públicas deben definirse el responsable del
umbral, el aprobador, el canal, el manejo de falsos positivos y los estados de
la alerta.

### G4. Aceptación

Antes de declarar finalizado el prototipo deben definirse escenarios y umbrales
de rendimiento, usabilidad, restauración y aceptación externa.

## 8. Riesgos principales

### R-01. Falta de autorización para datos sensibles

**Respuesta:** bloquear su carga y utilizar datos agregados o sintéticos hasta
contar con autorización formal.

### R-02. Granularidad insuficiente para radio censal

**Respuesta:** conservar el resultado departamental y presentar la distribución
espacial únicamente como simulación experimental.

### R-03. Confusión entre observado, sintético y predicho

**Respuesta:** aplicar nombres, metadatos, contratos, advertencias y estilos
visuales diferenciados en datasets, API y frontend.

### R-04. Fuga temporal o desempeño aparente

**Respuesta:** exigir cortes temporales, features disponibles al momento de
predicción y comparación con baselines.

### R-05. Reidentificación en la capa pública

**Respuesta:** agregar o suprimir en backend, revisar payloads y nunca enviar
datos detallados al navegador público.

### R-06. Publicación automática de alertas

**Respuesta:** usar una máquina de estados con aprobación administrativa y
auditoría obligatorias.

### R-07. Dependencia de servicios externos

**Respuesta:** registrar procedencia, usar importaciones por lote o caché y
mostrar degradación explícita cuando una fuente no esté disponible.

### R-08. Evidencia de validación incompleta

**Respuesta:** definir casos de prueba durante cada etapa y consolidarlos en la
matriz de trazabilidad final.

## 9. Definición de terminado del prototipo

SIGARD `v0.1` se considera técnicamente terminado cuando:

1. Los seis módulos comprometidos están operativos en el ambiente de prueba.
2. La interfaz pública funciona sin cuenta y no expone información individual.
3. Las operaciones administrativas exigen autenticación y autorización.
4. Los accesos y cambios sensibles quedan auditados.
5. Los pipelines son deterministas, reproducibles y preservan procedencia.
6. Los modelos se evalúan temporalmente frente a baselines.
7. La visualización diferencia contexto, simulación y predicción.
8. Ninguna alerta se publica sin aprobación administrativa.
9. El contenido sanitario conserva fuente, revisión y vigencia.
10. Se demuestran retención, eliminación y restauración en pruebas.
11. Rendimiento y usabilidad se evalúan con escenarios e instrumentos definidos.
12. Cada RF y RNF en alcance se vincula con una prueba y una evidencia.
13. Las limitaciones del target espacial sintético aparecen en documentación,
    API e interfaz.

## 10. Situación de verificación al iniciar el plan

- La existencia de pruebas no implica que la suite completa esté certificada.
- Las pruebas backend requieren instalar las dependencias de
  `backend/requirements.txt` en un entorno apropiado; no deben evaluarse usando
  automáticamente el entorno virtual exclusivo de ML.
- La validación Docker requiere crear `backend/.env` desde su ejemplo y
  reemplazar secretos antes de levantar servicios.
- El frontend dispone de dependencias y scripts de `lint` y `build`, pero aún
  deben reunirse evidencias de pruebas visuales, responsive, teclado y lector de
  pantalla.
- La evaluación ML vigente es exploratoria y no valida una distribución
  epidemiológica real por radio censal.

## 11. Supuestos de planificación

- El horizonte de 16 semanas representa el proyecto completo, no únicamente el
  trabajo pendiente desde el estado actual.
- El equipo base está compuesto por dos integrantes; cualquier reducción de
  disponibilidad requiere recalcular las duraciones.
- Las etapas mantienen el orden solicitado. Las revisiones de documentación,
  seguridad y pruebas se realizan también de forma transversal.
- Se reutiliza el código existente siempre que cumpla los contratos y criterios
  de aceptación; no se reimplementan componentes sólo para ajustarlos al orden
  del cronograma.
- La selección de infraestructura para FastAPI y PostGIS queda fuera de Vercel
  y debe resolverse antes de una demostración remota.
- Ninguna decisión pendiente se presenta como validada por el Ministerio de
  Salud sin evidencia documental.
