# Atajos del proyecto (J-02, ampliado en S-03).
#
# Dos pilas (variable STACK):
#   STACK=single (por defecto)  Compose raíz: una bodega + dev central, `docker compose up`.
#   STACK=multi                 Tres bodegas (WH-001/002/003) + RabbitMQ + central, proyecto "warehouses-demo".
# Atajos: `make up-multi`, `make down-multi`, `make ps-multi`...
#
# Ejemplos:
#   make up STACK=multi            levanta las 3 bodegas y la central
#   make logs s=wh002_api STACK=multi
#   make load STACK=multi WH=2 USERS=100 TIME=1m
#   make up STACK=multi PROFILES="obs"   (perfiles extra; ver docs/fases/fase-4.md)
#   make up STACK=multi PROFILES="lb"    (3 réplicas de WH-002 detrás de nginx en el 8002; ver fase-5.md)
.PHONY: up down logs reset-db ps test load up-multi down-multi ps-multi logs-multi reset-db-multi

STACK ?= single
PROJECT ?= warehouses-demo
PROFILES ?=
PROFILE_FLAGS := $(foreach p,$(PROFILES),--profile $(p))
CF := infrastructure/compose

ifeq ($(STACK),multi)
DC = docker compose -p $(PROJECT) -f $(CF)/compose.distributed.yml -f $(CF)/compose.central.yml \
     $(if $(findstring obs,$(PROFILES)),-f $(CF)/compose.obs.yml) $(PROFILE_FLAGS)
else
DC = docker compose $(PROFILE_FLAGS)
endif

up:
	$(DC) up --build -d

down:
	$(DC) down

# Estado de los contenedores (con STACK=multi se ve healthy/unhealthy de cada bodega).
ps:
	$(DC) ps

# Uso: make logs s=wh002_api   (sin s= muestra todos los servicios)
logs:
	$(DC) logs -f --tail=100 $(s)

# Pruebas unitarias en un venv local (.venv).
test:
	@test -d .venv || python3 -m venv .venv
	.venv/bin/pip install -q -r requirements-dev.txt
	.venv/bin/python -m pytest tests/unit

# Carga con Locust contra una bodega. Con STACK=multi corre dentro de la red de la bodega WH=1|2|3.
# Resultados CSV en docs/evidencias/fase-4/load-wh<WH>*. Variables: WH, USERS, TIME, SCENARIO.
WH ?= 1
USERS ?= 50
TIME ?= 1m
SCENARIO ?= ReadSameSku
load:
ifeq ($(STACK),multi)
	@mkdir -p docs/evidencias/fase-4
	docker run --rm --network $(PROJECT)_wh00$(WH) \
	  -v "$(CURDIR)/tests/load:/mnt/locust:ro" -v "$(CURDIR)/docs/evidencias/fase-4:/results" \
	  -e API_KEY=$${API_KEY:-dev-api-key} locustio/locust:2.32.5 \
	  -f /mnt/locust/locustfile.py --headless -u $(USERS) -r $(USERS) -t $(TIME) \
	  --host http://wh00$(WH)_api:8000 --csv /results/load-wh00$(WH) $(SCENARIO)
else
	docker compose --profile load run --rm locust
endif

# schema.sql, migrations/ y seed/ solo corren cuando el volumen de PostgreSQL
# está vacío. Para aplicar cambios en ellos hay que recrear la base:
# BORRA los datos de la base local (solo del proyecto seleccionado por STACK).
reset-db:
	$(DC) down -v
	$(DC) up --build -d

up-multi:
	$(MAKE) up STACK=multi
down-multi:
	$(MAKE) down STACK=multi
ps-multi:
	$(MAKE) ps STACK=multi
logs-multi:
	$(MAKE) logs STACK=multi
reset-db-multi:
	$(MAKE) reset-db STACK=multi
