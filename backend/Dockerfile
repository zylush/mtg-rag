FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY pyproject.toml ./
COPY app ./app

RUN python -m pip install --upgrade "pip>=26.1.2,<27"

FROM base AS test

ENV HOME=/tmp MYPY_CACHE_DIR=/tmp/mypy-cache RUFF_CACHE_DIR=/tmp/ruff-cache

COPY alembic.ini ./
COPY migrations ./migrations
COPY tests ./tests
COPY evals ./evals

RUN python -m pip install ".[dev]"
RUN chown -R app:app /app

USER app

CMD ["pytest", "--cov=app", "--cov-branch", "--cov-report=term-missing"]

FROM base AS wheel-builder

RUN python -m pip wheel --wheel-dir /wheels .

FROM base AS runtime

COPY --from=wheel-builder /wheels /wheels
COPY alembic.ini ./
COPY migrations ./migrations
COPY evals ./evals

RUN python -m pip install --no-index --find-links=/wheels mtg-rag-api && python -m pip uninstall -y setuptools wheel && python -m pip uninstall -y pip && rm -rf /wheels

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--timeout-keep-alive", "10"]
