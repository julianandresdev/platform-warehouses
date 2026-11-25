FROM python:3.12-slim

WORKDIR /app

# Instalar las dependencias de la Central API
COPY central/requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Instalar el paquete compartido del proyecto
COPY common /tmp/common

RUN pip install --no-cache-dir /tmp/common \
    && rm -rf /tmp/common

# Copiar el código de la plataforma central
COPY central/app/ /app/app/

# Puerto interno de FastAPI
EXPOSE 8000

# Iniciar el servidor
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
