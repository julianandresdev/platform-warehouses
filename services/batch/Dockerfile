FROM python:3.12-slim

WORKDIR /app

COPY batch/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY batch/ .
COPY batch/batch/ /app/batch/
COPY common/common/ /app/common/

CMD ["python", "main.py"]
