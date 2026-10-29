FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends antiword nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Optional, isolated architecture-kit runtime retained for rollback.
ARG INSTALL_AWS_ARCH_KIT=false
COPY backend/config/requirements_arch_kit.txt /tmp/requirements_arch_kit.txt
RUN if [ "$INSTALL_AWS_ARCH_KIT" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends graphviz \
      && python -m venv /opt/aws-arch-kit \
      && /opt/aws-arch-kit/bin/pip install --no-cache-dir -r /tmp/requirements_arch_kit.txt \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY backend/config/requirements_clean.txt /app/backend/config/requirements_clean.txt

RUN pip install --no-cache-dir \
    -r /app/backend/config/requirements_clean.txt

COPY . /app

RUN npm ci --prefix /app/tools/architecture-layout --omit=dev --ignore-scripts --no-audit --no-fund

ENV ARCHITECTURE_DIAGRAM_ENGINE=hybrid

WORKDIR /app/backend

CMD ["sh", "-c", "gunicorn --workers 1 --threads 8 --timeout 1200 --bind 0.0.0.0:${PORT:-10000} app.core.server:app"]
