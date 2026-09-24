# Iteración 11: persistencia y API pública

## Objetivo

Publicar mediante FastAPI los artefactos epidemiológicos aprobados que hoy
consume React desde `frontend/public/data/`, conservando su versión,
procedencia y condición observada, sintética o predicha. El backend no entrena,
simula ni recalcula resultados durante una solicitud.

## Estado de partida

- PostgreSQL/PostGIS, FastAPI y React funcionan como servicios saludables.
- Alembic administra el esquema operativo de usuarios y reportes ciudadanos.
- ML se ejecuta offline y exporta contratos públicos reproducibles.
- React valida alineación temporal, niveles permitidos y 263 radios, pero lee
  archivos estáticos.
- `citizen_reports` permanece aislado del dominio epidemiológico.

## Avance

- [x] 11.1 Contrato, modelos y migración PostGIS.
- [x] 11.2 Importador offline transaccional e idempotente.
- [x] 11.3 API pública con caché, versión y respuestas controladas.
- [x] 11.4 React usa la API primero y conserva un fallback estático explícito.
- [x] 11.5 Evidencia visual en navegador y mapa epidemiológico sin dependencia
  de teselas externas.
- [x] 11.6 Prueba controlada desde una base temporal vacía y cierre de la
  matriz de verificación.

## Decisiones de alcance

- La unidad de publicación es un lote inmutable y versionado.
- Sólo un lote aprobado puede quedar activo para la API pública.
- La geometría censal se almacena una vez por radio y versión territorial.
- La simulación semanal referencia el radio; no duplica conceptualmente la
  geometría ni se presenta como observación.
- La carga es un comando offline, transaccional e idempotente.
- Los artefactos estáticos continúan como fallback hasta cerrar la migración
  del frontend.
- Alertas y contenido sanitario editable quedan fuera de esta iteración.

## Mini-plan

### 11.1 Contrato y esquema

Definir modelos y una migración Alembic para:

- lote de publicación y metadatos metodológicos;
- semanas disponibles;
- predicciones temporales departamentales;
- radios y contexto territorial versionado;
- resultados de la simulación espacial experimental por radio y semana.

Restricciones mínimas:

- unicidad de corte dentro de un lote;
- unicidad de radio en el contexto territorial;
- unicidad de `radio + corte` en la simulación;
- valores no negativos y niveles `very_low`, `low`, `medium`, `high`;
- geometrías EPSG:4326 válidas;
- estados del lote `staged`, `published` o `retired`.

### 11.2 Importador offline

Crear un comando temporal que lea exclusivamente los seis contratos aprobados:

- `available_weeks.json`;
- `temporal_predictions.json`;
- `territorial_context.geojson`;
- `experimental_spatial_history.geojson`;
- `model_evaluation.json`;
- `mvp_metadata.json`.

Antes de escribir debe comprobar:

- coincidencia exacta de corte, inicio y fin de semana;
- una predicción y 263 radios experimentales por semana publicada;
- 263 radios únicos en el contexto territorial;
- identificadores coincidentes entre ambas capas;
- niveles relativos permitidos;
- ausencia de campos privados o administrativos;
- hash del conjunto de entradas para reconocer reintentos.

La publicación se confirma en una transacción. Un error no deja un lote
parcial ni reemplaza el lote activo.

### 11.3 API pública

Implementar inicialmente:

```text
GET /api/v1/public/weeks
GET /api/v1/public/predictions/{cutoff_date}
GET /api/v1/public/territorial-context
GET /api/v1/public/experimental-spatial-history/{cutoff_date}
GET /api/v1/public/metadata
GET /api/v1/public/model-evaluation
```

Las respuestas deben derivar únicamente del lote publicado e incluir versión,
procedencia y advertencias. Fechas inexistentes responden `404`; parámetros
inválidos, `422`; ausencia de un lote publicado, `503`.

### 11.4 Migración gradual del frontend

- Incorporar un cliente para la API pública usando `VITE_API_URL`.
- Mantener temporalmente el contrato estático como fallback explícito.
- Conservar las validaciones de alineación y cantidad de radios en el cliente.
- Mostrar estados diferenciados de carga, API no disponible y contrato
  incompatible.
- Retirar el fallback sólo después de probar el arranque desde una base vacía.

### 11.5 Verificación y cierre

- Pruebas unitarias del importador sin PostgreSQL.
- Pruebas de API positivas, `404`, `422` y `503`.
- Prueba de privacidad de todos los payloads públicos.
- Migración y carga repetibles sobre PostgreSQL/PostGIS.
- Recorrido integrado navegador → FastAPI → PostgreSQL.
- Comparación estructural entre respuestas API y contratos estáticos.
- Actualización de OpenAPI, arquitectura, contrato de datos y operación Docker.

## Criterio de aceptación

Desde una base vacía se pueden aplicar las migraciones, importar un lote
aprobado y consultar desde React las mismas cuatro semanas y capas que ofrece
el MVP estático. El proceso no modifica `data/raw/`, no entrena modelos, no
mezcla reportes ciudadanos con datos epidemiológicos y no publica datos
individualizables. Repetir la importación no duplica registros ni cambia el
resultado activo.

## Evidencia de cierre

La verificación local del 24 de septiembre de 2026 confirmó:

- revisión Alembic `20260924_03 (head)`;
- 13 pruebas del backend aprobadas;
- carga repetida sin duplicar el lote activo;
- 4 semanas, 4 predicciones, 263 radios y 1.052 filas experimentales;
- arranque completo sobre una base temporal vacía con PostGIS habilitado;
- frontend construido sin errores y rutas principales con respuesta `200`;
- mapa cargado desde la API, versión visible y sin teselas externas;
- consola del navegador sin errores ni advertencias;
- eliminación de todas las bases temporales usadas para la prueba.

## Fuera de alcance

- Validación epidemiológica espacial real.
- Generación o aprobación de alertas.
- Edición administrativa de contenido sanitario.
- Automatización de entrenamiento o despliegue productivo.
