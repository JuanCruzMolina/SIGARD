cat > README.md << 'READMEEOF'
# SIGARD

**Sistema Informático para la Geolocalización y Alerta de Zonas de Riesgo por Dengue — La Rioja Capital**

Universidad Nacional de La Rioja — Ingeniería en Sistemas de Información — 2025

## Autores

- Dominguez Sotomayor, Santiago Ismael
- Molina Leguiza, Juan Cruz

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python + FastAPI |
| Base de datos | PostgreSQL + PostGIS |
| Frontend | React + Leaflet |
| Machine Learning | scikit-learn + XGBoost |
| Infraestructura | Docker + Docker Compose |

## Levantar el proyecto

```bash
cp backend/.env.example backend/.env
docker-compose up --build
```

## URLs

- Frontend: http://localhost:5173
- API: http://localhost:8000
- Documentación API: http://localhost:8000/docs

## Estructura del proyecto

    sigard/
    ├── backend/     FastAPI + modelos de base de datos
    ├── frontend/    React + Leaflet (mapas interactivos)
    ├── ml/          Modelos predictivos y experimentos
    ├── data/        Datos epidemiológicos (no versionados)
    └── docs/        Documentación técnica
READMEEOF
