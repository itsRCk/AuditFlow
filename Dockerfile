# The API runs as one persistent service: SQL jobs, local OCR, and a mounted file store.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AUDITFLOW_DATA_DIR=/data \
    AUDITFLOW_SEED_DEMO=true \
    PORT=8000

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 auditflow \
    && useradd --uid 10001 --gid auditflow --no-create-home auditflow \
    && mkdir /data \
    && chown auditflow:auditflow /data

COPY requirements-runtime.lock ./
# Optional build-only CA bundle for environments with an HTTPS inspection proxy.
# It is never copied into the image; ordinary hosting builds need no secret.
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -f /run/secrets/build_ca_bundle ]; then export PIP_CERT=/run/secrets/build_ca_bundle; fi; \
    pip install --no-cache-dir --require-hashes -r requirements-runtime.lock
COPY --chown=auditflow:auditflow server ./server
COPY --chown=auditflow:auditflow public/favicon.svg ./public/favicon.svg
USER auditflow

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request,json; data=json.load(urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health',timeout=4)); assert data['status']=='ok' and data['worker_alive']"

# Use one process per mounted SQLite database. The hosting service controls PORT.
CMD ["sh", "-c", "exec uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
