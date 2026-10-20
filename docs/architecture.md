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

La [preparación espacial oficial de Fase 5A](official-spatial-ml.md) corre offline
en `sigard_ml.official.spatial_ml`, reutilizando los paneles y auditorías privados
preservados. Separa ingeniería de características, construcción, validación,
diagnóstico y particiones cronológicas. Escribe exclusivamente en una carpeta
nueva de `data/processed/official/`, excluida de Git/Docker. No entrena, no genera
ceros, no reingiere fuentes y no modifica el modelo temporal departamental,
el modelo espacial sintético, la API ni el frontend. Su dataset es retrospectivo
y provisional; la disponibilidad histórica y los negativos respaldados siguen
siendo requisitos previos al entrenamiento.

### Preparación y machine learning

La [Fase 5B](official-spatial-experiment.md) añade módulos independientes de
auditoría/selección, faltantes, elegibilidad/cobertura propuesta y protocolo del
experimento. Reutiliza Fase 5A y configuración de Fase 4.3, conserva sus archivos
y sólo escribe diagnósticos/configuraciones privados en un destino nuevo de
`data/interim/official/`. La preparación no importa entrenadores existentes,
no ejecuta `fit` y mantiene bloqueada la materialización de negativos asumidos.

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

El circuito territorial oficial en `sigard_ml.official` está separado del
recorrido sintético. La [fase 2](official-ingestion.md) incorpora lectura y
calidad local de fuentes autorizadas; conserva registros cuya unidad está
pendiente de definición. El panel observado radio-semana, entrenamiento y
publicación requieren fases y aprobaciones posteriores. La
[arquitectura de fase 1](official-pipeline.md) documenta los contratos base.

La [fase 3](official-geography.md) reutiliza esos normalizados y la cartografía
vigente para un diagnóstico geográfico privado. Separa lectura autorizada,
auditoría cartográfica, coincidencia espacial, incertidumbre y reportes. Sus
salidas permanecen en `data/interim/official/`; una coincidencia interior única
no convierte la fila en caso elegible ni valida precisión epidemiológica.

La [fase 4](official-observed-panel.md) agrega un panel exploratorio retrospectivo
privado. Reutiliza normalizados y asignaciones, recupera referencias opacas de
identidad, separa clasificación, elegibilidad, episodio, fecha y cobertura, y
concilia todas las filas. La opción explícita `--exploratory` habilita reglas
provisionales y candidatos aproximados conforme a la decisión del proyecto.
El modo conservador no incorpora registros sin validación epidemiológica.
Ambos preservan null y cobertura; el panel validado y el entrenamiento siguen
pendientes. El objetivo futuro oficial es probabilidad de registro en la semana
siguiente, independiente de los modelos, objetivos y artefactos vigentes.

La [fase 4.1](official-date-recovery.md) reutiliza ese constructor para comparar
una regla estricta con una jerarquía explícita de fechas identificadas. Mantiene
el panel anterior y escribe versiones privadas independientes, con procedencia
temporal por fila y verificación de conciliación. No geocodifica, modifica modelos,
entrena ni cambia contratos de frontend/backend.

La [fase 4.2](official-coverage.md) consume los paneles y auditorías privados de
Fase 4.1. Separa declaraciones de procedencia, cobertura declarada y resoluciones
de cobertura comprobada; construye escenarios de ceros conservador/exploratorio
para fechas estrictas/ampliadas y un objetivo binario de la semana siguiente.
Preserva null, bloquea ceros afectados por pendientes y conserva incertidumbre.
El diagnóstico es retrospectivo, sin entrenamiento ni métricas predictivas.

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

La gestión de cuentas de etapa 14 reutiliza esa interfaz y `usuarios`. La API
`/api/v1/admin/users` requiere JWT, cuenta activa, versión de sesión vigente y
rol `admin`; las mutaciones requieren además la contraseña del actor. Una
transacción serializa los cambios, protege al último administrador y registra
auditoría sin credenciales. Desactivación y rotación revocan los tokens previos.
El bootstrap sólo inicia una tabla de usuarios vacía. La migración versionada
queda preparada, sin aplicación a bases persistentes. El contrato y las pruebas
se detallan en [backend/README.md](../backend/README.md#cuentas-administrativas-y-autenticación--etapa-14).
Este circuito no participa en el acceso público ni en la API local A/B.
