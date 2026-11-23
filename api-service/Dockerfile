# Build context MUST be the repo root, e.g.:
#   docker build -f api-service/Dockerfile -t api-service .
FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the shared nepse-common package first so its layer is cached
# independently of api-service source changes.
COPY nepse-common /nepse-common
RUN pip install --no-cache-dir -e /nepse-common

# Then the service's own dependencies, from its pyproject.toml alone, so this
# layer is rebuilt only when the dependencies (or nepse-common) change, not on
# every code change. The project ships no modules (packages = []), so pip
# installs just its dependencies; "nepse-common" is satisfied by the install
# above. Built outside /app so no build/ or *.egg-info is left in the image.
COPY api-service/pyproject.toml /tmp/api-service/pyproject.toml
RUN pip install --no-cache-dir /tmp/api-service && rm -rf /tmp/api-service

COPY api-service /app

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
