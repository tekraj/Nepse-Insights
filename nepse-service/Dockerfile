# Build context MUST be the repo root, e.g.:
#   docker build -f nepse-service/Dockerfile -t nepse-service .
FROM python:3.14-slim

# Without this, Python fully block-buffers stdout when it isn't a TTY (true
# inside a container), so `docker logs` / `docker-compose logs` can sit
# silent for minutes at a time even while the worker is actively processing
# -- confirmed directly on the pre-split scraper-service: real backfill
# progress was happening with zero corresponding log output visible.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the shared nepse-common package first so its layer is cached
# independently of nepse-service source changes.
COPY nepse-common /nepse-common
RUN pip install --no-cache-dir -e /nepse-common

# Then the service's own dependencies, from its pyproject.toml alone, so this
# layer is rebuilt only when the dependencies (or nepse-common) change, not on
# every code change. The project ships no modules (packages = []), so pip
# installs just its dependencies; "nepse-common" is satisfied by the install
# above. Built outside /app so no build/ or *.egg-info is left in the image.
COPY nepse-service/pyproject.toml /tmp/nepse-service/pyproject.toml
RUN pip install --no-cache-dir /tmp/nepse-service && rm -rf /tmp/nepse-service

COPY nepse-service /app

# historical-data holds the checked-in NEPSE CSV exports imported by
# HistoricalNepseCsvImportWorkflow on startup (moved here from
# scraper-service/news-service along with the rest of the NEPSE-specific
# code -- see HISTORICAL_NEPSE_CSV_DIR in nepse_common/config.py).
RUN mkdir -p historical-data logs

CMD ["python", "worker.py"]
