# Contexto de build: services/ (para poder instalar el paquete common).
#   docker build -f batch/Dockerfile services/
FROM python:3.12-slim

WORKDIR /app

COPY common /tmp/common
RUN pip install --no-cache-dir /tmp/common && rm -rf /tmp/common

COPY batch/ .

CMD ["python", "-m", "batch.daily_report"]
