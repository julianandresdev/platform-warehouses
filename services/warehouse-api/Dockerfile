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

# --limit-concurrency: por encima de ese número de conexiones/tareas, uvicorn responde 503
# al instante en vez de encolar. Sin él, bajo sobrecarga los requests se acumulan en la cola
# del pool de hilos (se vieron de 185 s) y la réplica tarda minutos en drenar (J-06 / J-09).
ENV UVICORN_LIMIT_CONCURRENCY=200
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port 8000 --limit-concurrency ${UVICORN_LIMIT_CONCURRENCY}"]
