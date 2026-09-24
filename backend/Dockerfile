FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.runtime.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.runtime.txt

RUN useradd --system --create-home sigard

COPY --chown=sigard:sigard app/ ./app/
COPY --chown=sigard:sigard migrations/ ./migrations/
COPY --chown=sigard:sigard alembic.ini ./

FROM base AS runtime

USER sigard

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM runtime AS test

USER root
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY --chown=sigard:sigard tests/ ./tests/
USER sigard

CMD ["pytest", "-q", "-p", "no:cacheprovider"]
