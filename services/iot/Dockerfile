FROM python:3.12-slim

WORKDIR /app

COPY iot/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY common/common /app/common
COPY iot/app /app/app

ENV PYTHONPATH=/app

CMD ["python", "-m", "iot.simulator"]
