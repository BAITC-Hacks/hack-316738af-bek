# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY . /source
RUN if [ -f /source/frontend/package.json ]; then \
      test -f /source/frontend/package-lock.json || (echo 'frontend/package-lock.json is required' >&2; exit 1); \
      cp -a /source/frontend/. /build/ && npm ci && npm run build; \
    else mkdir -p /build/dist; fi

FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt /tmp/backend-requirements.txt
# .dockerignore excludes secrets, uploaded material and developer virtual environments.
COPY . /tmp/source
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1 && \
    if [ -f /tmp/source/ai_engine/requirements.txt ]; then \
      python -m pip install --no-cache-dir -r /tmp/backend-requirements.txt -r /tmp/source/ai_engine/requirements.txt; \
    else python -m pip install --no-cache-dir -r /tmp/backend-requirements.txt; fi && \
    cp -a /tmp/source/backend /app/backend && cp -a /tmp/source/contracts /app/contracts && \
    if [ -d /tmp/source/ai_engine ]; then cp -a /tmp/source/ai_engine /app/ai_engine; fi && \
    rm -rf /tmp/source && \
    useradd --create-home --uid 10001 qurylym && mkdir -p /data && chown 10001:10001 /data
COPY --from=frontend /build/dist /app/frontend/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/health', timeout=3)"
CMD ["python", "-m", "backend.app.serve"]
