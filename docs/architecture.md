# Arquitectura conceptual de SIGARD v0.1

## Propósito

La arquitectura de `v0.1` valida un recorrido técnico reproducible desde
fuentes heterogéneas hasta una visualización espacio-temporal. La unidad que
conecta todas las capas es **radio censal - semana epidemiológica**.

## Flujo previsto

```text
Fuentes reales inmutables
        |
        v
Validación y normalización
        |
        +--> totales observados de Capital por semana
        |
        v
Asignación sintética reproducible por radio
        |
        v
Panel radio-semana y features temporales
        |
        v
Entrenamiento y evaluación temporal (fuera del backend)
        |
        v
Predicciones versionadas para la semana siguiente
        |
        +--> API FastAPI --> frontend Leaflet
        |
        +--> PostgreSQL/PostGIS
```

Las coordenadas puntuales sintéticas son una rama de visualización derivada de
la asignación por radio. No intervienen en el entrenamiento ni representan
domicilios o ubicaciones observadas.

## Responsabilidades por componente

### Preparación y machine learning

- valida y normaliza las fuentes;
- construye el panel radio-semana;
- genera asignaciones sintéticas con semillas deterministas;
- crea features sin usar información futura;
- entrena y evalúa con cortes temporales;
- publica datasets y artefactos versionados para consumo.

Este componente funciona como proceso offline. El entrenamiento no se ejecuta
al iniciar la API ni como parte de una solicitud HTTP.

### Persistencia

PostgreSQL/PostGIS almacena lotes de publicación versionados, semanas,
predicciones temporales departamentales, contexto territorial y resultados de
la simulación espacial experimental. Las geometrías censales se conservan una
vez por radio y lote; los resultados semanales las referencian sin presentarlas
como ubicaciones observadas.

### API

FastAPI expone resultados ya preparados desde el único lote marcado como
publicado. No asigna casos, entrena modelos ni genera puntos sintéticos en
tiempo de solicitud.

### Frontend

React con Leaflet muestra radios, semanas y predicciones desde la API pública.
Conserva temporalmente los contratos estáticos como respaldo explícito. Las
capas sintéticas se identifican visualmente como experimentales. El frontend
está previsto para Vercel; API y PostGIS requieren infraestructura separada.

## Fronteras de información

La arquitectura conserva tres conceptos diferentes:

1. observación real: total de casos de Capital para un año-semana;
2. asignación sintética: reparto de ese total entre radios;
3. predicción: cantidad estimada por el modelo para un radio-semana futuro.

Ninguna tabla, endpoint, archivo o etiqueta de interfaz debe usar un único campo
ambiguo `casos` para representar los tres conceptos.

## Artefactos y seguridad

No se incorporan a Git fuentes de datos, datasets derivados, artefactos de
modelos, secretos ni archivos `.env`. El repositorio sólo conserva código,
configuración no sensible, contratos, metadatos y documentación.

## Módulo informativo y de participación ciudadana

La ruta pública `/prevencion` constituye una rama independiente del flujo
epidemiológico. Consume dos artefactos estáticos versionados y una API
operativa:

```text
Fuentes sanitarias oficiales --> contenido preventivo y directorio público
                                          |
Ciudadanía --> formulario anónimo --> API | --> citizen_reports (privado)
                                          |
                         código público --+--> estado sin ubicación ni texto
                                          |
                         JWT + rol admin --+--> bandeja, auditoría y exportación
```

`citizen_reports` no se conecta con el panel `radio-semana`, las tablas de
casos, las asignaciones sintéticas ni las predicciones. La coordenada exacta se
usa sólo para revisión operativa autorizada y se elimina al vencer su plazo de
retención. En desarrollo, Compose ejecuta la purga como un trabajo temporal
bajo demanda; un despliegue operativo debe programar y supervisar su ejecución
diaria. Frontend y backend se despliegan por separado: Vercel puede alojar la
SPA, mientras FastAPI y PostgreSQL/PostGIS requieren otro servicio.

La superficie pública real es `/prevencion` y la operación protegida se realiza
en `/admin/reportes`. Hasta confirmar un organismo receptor, la API impide marcar
un reporte como `derivado` y el formulario se presenta sólo como registro interno
de SIGARD.
