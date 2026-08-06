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

PostgreSQL/PostGIS almacenará geometrías, unidades temporales, asignaciones
sintéticas y predicciones con su procedencia y versión. El esquema SQL actual
no representa todavía este contrato y se mantiene sin cambios durante esta
etapa documental.

### API

FastAPI expondrá resultados ya preparados y versionados. No asignará casos,
entrenará modelos ni generará puntos sintéticos en tiempo de solicitud.

### Frontend

React o Next.js con Leaflet mostrará radios, semanas y predicciones. Los puntos
sintéticos deberán identificarse visualmente como simulados. El frontend está
previsto para Vercel; API y PostGIS requerirán infraestructura separada.

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
