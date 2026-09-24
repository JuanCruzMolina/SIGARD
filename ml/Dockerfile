FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY pyproject.toml requirements.runtime.txt ./
COPY src/ ./src/

RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.runtime.txt \
    && pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0

WORKDIR /workspace

COPY --from=builder /wheels/ /wheels/
RUN pip install --no-cache-dir --disable-pip-version-check \
        --no-index --find-links=/wheels sigard-ml==0.1.0 \
    && rm -rf /wheels \
    && useradd --system --create-home sigardml \
    && mkdir -p /workspace/data/interim \
        /workspace/data/processed \
        /workspace/ml/artifacts \
        /workspace/frontend/public/data \
    && chown -R sigardml:sigardml /workspace

COPY --chown=sigardml:sigardml configs/ /workspace/ml/configs/

USER sigardml

CMD ["python", "-m", "sigard_ml.evaluation.department_temporal_pipeline", "--help"]
