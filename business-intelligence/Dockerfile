# Build context MUST be the repo root, e.g.:
#   docker build -f business-intelligence/Dockerfile -t business-intelligence .
FROM python:3.14-slim

# Unbuffered stdout so `docker compose logs` shows agent progress live.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the shared nepse-common package first so its layer is cached
# independently of business-intelligence source changes.
COPY nepse-common /nepse-common
RUN pip install --no-cache-dir -e /nepse-common

# Then the service's own dependencies, from its pyproject.toml alone, so this
# layer is rebuilt only when the dependencies (or nepse-common) change, not on
# every code change. The project ships no modules (packages = []), so pip
# installs just its dependencies; "nepse-common" is satisfied by the install
# above. Built outside /app so no build/ or *.egg-info is left in the image.
COPY business-intelligence/pyproject.toml /tmp/business-intelligence/pyproject.toml
RUN pip install --no-cache-dir /tmp/business-intelligence && rm -rf /tmp/business-intelligence

COPY business-intelligence /app

EXPOSE 50051

# gRPC server (api-service's client) + Temporal worker (24/7 automation).
CMD ["python", "main.py"]
