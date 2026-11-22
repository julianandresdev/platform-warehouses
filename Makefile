# Atajos mínimos (J-02). S-03 lo amplía con ps, test y load.
.PHONY: up down logs reset-db

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

# schema.sql, migrations/ y seed/ solo corren cuando el volumen de PostgreSQL
# está vacío. Para aplicar cambios en ellos hay que recrear la base:
# BORRA los datos de la base local.
reset-db:
	docker compose down -v
	docker compose up --build -d
