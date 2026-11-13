# syntax=docker/dockerfile:1
# AgentGate backend (Django) production image.
# PayPal is intentionally excluded: this image is built from `intergration`,
# which contains no PayPal routes or configuration.

FROM python:3.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies for psycopg (libpq) and health checks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN groupadd --system agentgate && useradd --system --gid agentgate --create-home agentgate

WORKDIR /app

# Install Python dependencies reproducibly.
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Application code.
COPY backend/ /app/

# Writable directories for runtime artifacts.
RUN mkdir -p /app/staticfiles /app/media && chown -R agentgate:agentgate /app

# Entrypoint (runs collectstatic, then execs CMD).
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER agentgate

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        try: urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4); sys.exit(0) \
        except Exception: sys.exit(1)"

# Default command is overridden by compose for web vs worker.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--access-logfile", "-"]
