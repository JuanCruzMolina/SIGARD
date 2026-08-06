# SIGARD

SIGARD es un prototipo de predicción espacio-temporal de posibles casos de
dengue por radio censal en La Rioja Capital. Su versión `v0.1` tiene como
propósito validar el flujo técnico completo —preparación de datos,
entrenamiento, publicación de predicciones y visualización geográfica— y no
producir inferencias epidemiológicas operativas.

## Alcance de v0.1

La unidad analítica principal es el par **radio censal - semana
epidemiológica**. El objetivo futuro del modelo es predecir la cantidad de
casos asignados a cada radio para la semana epidemiológica siguiente.

SIGARD combina las siguientes fuentes reales:

- geometrías oficiales de radios censales;
- población, hogares y viviendas por radio;
- casos de dengue agregados para Capital por año y semana epidemiológica;
- clima histórico.

Como no se dispone de la ubicación real de los casos dentro de Capital, el
prototipo genera dos clases de datos sintéticos:

- asignación de los totales semanales observados entre radios censales;
- coordenadas puntuales dentro de cada radio, usadas exclusivamente para
  visualización.

Debe distinguirse siempre entre casos observados agregados de Capital, casos
asignados sintéticamente por radio y predicciones producidas por el modelo.

## Límite metodológico

La distribución espacial usada como objetivo de entrenamiento es sintética.
Por ello, el prototipo puede demostrar que el pipeline y la arquitectura
funcionan, pero **no demuestra capacidad epidemiológica real para localizar
casos de dengue por radio censal**. Sus resultados no deben utilizarse para
decisiones sanitarias ni interpretarse como ubicaciones reales de personas.

## Arquitectura prevista

| Capa | Tecnología prevista |
| --- | --- |
| Preparación y ML | Python, pandas y scikit-learn (Random Forest) |
| API | FastAPI |
| Persistencia espacial | PostgreSQL y PostGIS |
| Visualización | React o Next.js con Leaflet |
| Despliegue web | Vercel para el frontend |

El entrenamiento se ejecutará fuera del backend. La API sólo consumirá
artefactos ya generados y publicará resultados versionados.

## Estado actual

El repositorio contiene scaffolding inicial para backend, frontend, ML y
Docker. En esta etapa se establece únicamente la base documental y el contrato
conceptual de `v0.1`; todavía no existe un pipeline integrado ni un modelo
entrenado.

## Documentación

- [Arquitectura](docs/architecture.md)
- [Contrato de datos](docs/data-contract.md)
- [Metodología](docs/methodology.md)
- [Datos sintéticos](docs/synthetic-data.md)
- [Política del directorio de datos](data/README.md)

## Reglas del repositorio

- Los datos en `data/raw/` son inmutables.
- Los procesos aleatorios deben usar semillas explícitas y deterministas.
- La evaluación será temporal; nunca se dividirán filas aleatoriamente.
- Toda feature debe respetar el tiempo de disponibilidad para evitar data
  leakage.
- No se versionan datasets, artefactos de modelos, secretos ni archivos `.env`.
- Los datos sintéticos y las predicciones deben estar rotulados como tales.

## Autores

- Dominguez Sotomayor, Santiago Ismael
- Molina Leguiza, Juan Cruz

Universidad Nacional de La Rioja — Ingeniería en Sistemas de Información.
