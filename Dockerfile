# Arthentic Modular Monolith - Production & Local Staging Dockerfile (Wave 2 Milestone 4)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt psycopg2-binary redis

COPY alembic.ini /app/alembic.ini
COPY server /app/server
COPY scripts /app/scripts
COPY contracts /app/contracts

RUN chmod +x /app/scripts/docker_entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
