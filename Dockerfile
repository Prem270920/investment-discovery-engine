# Investment Discovery Engine: one image that serves the API and the built app.
#
# Build for Render's linux/amd64 servers, even from an Apple Silicon Mac:
#   docker buildx build --platform linux/amd64 -t discovery-engine --load .
#
# The image serves stored data only. It carries the SQLite database and the
# frozen cluster model, and leaves out torch: the GRU's results are already
# in the database, so the app shows both lenses without the library that
# trained them.

# Stage 1: build the frontend. Only frontend/dist leaves this stage.
FROM node:26-slim AS frontend
WORKDIR /build/frontend
# The lockfile first, so dependencies are reinstalled only when they change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the Python app.
FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# requirements.txt only: requirements-ml.txt (torch) stays out of the image.
COPY requirements.txt ./
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 discovery

COPY src/ ./src/
COPY config/ ./config/
COPY models/cluster_model.joblib ./models/cluster_model.joblib
COPY --from=frontend /build/frontend/dist ./frontend/dist
# The app user owns data/ so SQLite can write its journal beside the file if
# the pipeline is ever run in here; serving only reads.
COPY --chown=discovery:discovery data/investments.db ./data/investments.db
RUN chown discovery:discovery ./data

USER discovery

# Render sets PORT; 8000 everywhere else.
ENV PORT=8000
EXPOSE 8000

# slim has no curl, so the check uses Python's own HTTP client.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/health', timeout=4)"]

# A shell so ${PORT} is filled in; exec so uvicorn gets stop signals directly.
CMD ["sh", "-c", "exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
