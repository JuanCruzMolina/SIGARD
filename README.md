\# SIGARD

\*\*Sistema Informático para la Geolocalización y Alerta de Zonas de Riesgo por Dengue — La Rioja Capital\*\*



Universidad Nacional de La Rioja — Ingeniería en Sistemas de Información — 2025



\## Autores

\- Dominguez Sotomayor, Santiago Ismael

\- Molina Leguiza, Juan Cruz



\## Stack tecnológico

\- \*\*Backend:\*\* Python + FastAPI + PostgreSQL/PostGIS

\- \*\*Frontend:\*\* React + Leaflet

\- \*\*ML:\*\* scikit-learn, XGBoost, TensorFlow

\- \*\*Infraestructura:\*\* Docker + Docker Compose



\## Levantar el proyecto



Copiar los archivos de variables de entorno y luego ejecutar:



&#x20;   docker-compose up --build



\- API: http://localhost:8000

\- Frontend: http://localhost:5173

\- Docs API: http://localhost:8000/docs



\## Estructura



&#x20;   sigard/

&#x20;   ├── backend/     # FastAPI

&#x20;   ├── frontend/    # React + Leaflet

&#x20;   ├── ml/          # Modelos predictivos

&#x20;   ├── data/        # Datos (no versionados)

&#x20;   └── docs/        # Documentación técnica

