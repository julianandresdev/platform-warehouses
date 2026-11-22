# Contexto de build: services/ (para poder instalar el paquete common).
#   docker build -f warehouse-api/Dockerfile services/
FROM python:3.12-slim

WORKDIR /app

COPY warehouse-api/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY common /tmp/common
RUN pip install --no-cache-dir /tmp/common && rm -rf /tmp/common

COPY warehouse-api/ .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
