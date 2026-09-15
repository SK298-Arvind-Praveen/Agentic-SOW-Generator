FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/config/requirements_clean.txt /app/backend/config/requirements_clean.txt

RUN pip install --no-cache-dir \
    -r /app/backend/config/requirements_clean.txt

COPY . /app

WORKDIR /app/backend

CMD ["sh", "-c", "gunicorn --workers 1 --threads 8 --timeout 1200 --bind 0.0.0.0:${PORT:-10000} app.core.server:app"]