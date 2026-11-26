# Fase 4 - Múltiples bodegas

Líder: Santiago · Apoyo: David

Estado: S-03 cerrada (Compose con 3 bodegas, perfiles, `mem_limit` y Makefile).

## Qué se construyó

Cada bodega es un dominio autónomo: su API, sus workers, su PostgreSQL y su Redis, en una red Docker propia. Las tres comparten solo RabbitMQ (red `messaging`), como describe el [ADR-0007](../adr/0007-una-base-por-bodega.md). El Compose está en [`compose.distributed.yml`](../../infrastructure/compose/compose.distributed.yml) y los anchors (`x-api`, `x-db`, `x-redis`, `x-*-worker`) evitan repetir la definición por bodega.

Lo que cerró S-03 sobre lo que ya existía:

- **Un `.env` por bodega** (`infrastructure/compose/wh-001.env`, `wh-002.env`, `wh-003.env`) con `WAREHOUSE_ID` y `API_KEY`. Todos los servicios de la bodega (api, db, workers, comandos) los cargan con `env_file`; ya no hay `WAREHOUSE_ID` repetido en línea.
- **`mem_limit` por contenedor** (API 384 MiB, DB 512 MiB, workers 192 MiB, Redis y nginx 64 MiB, RabbitMQ 512 MiB), dimensionado con los `docker stats` de la [F11](../evidencias/fase-11/).
- **Puertos configurables** con variables (`WH001_PORT`, `WH003_PORT`, `NGINX_PORT`, `RABBITMQ_PORT`, `RABBITMQ_MGMT_PORT`) y los valores por defecto que ya usan la demo, los scripts y AWS. Las bases no publican ningún puerto.
- **`rabbitmq_topology`** ahora declara su red, así `compose.distributed.yml` arranca también sin el Compose central.
- **Makefile**: `ps`, `test`, `load` y `logs s=<servicio>`; `up`/`down`/`reset-db` pueden apuntar a las tres bodegas con `STACK=multi` (o `make up-multi`).
- **Seeds**: ya cumplían lo pedido. Las tres bodegas cargan el mismo catálogo de 10 SKU (`P-001`…`P-010`) con stock distinto; `P-001` vale 100 en WH-001, 20 en WH-002 y 55 en WH-003.

### Cómo levantarlo

```sh
make up STACK=multi            # 3 bodegas + RabbitMQ + central (proyecto warehouses-demo)
make ps STACK=multi
make logs STACK=multi s=wh002_api
make load STACK=multi WH=2 USERS=100 TIME=1m   # Locust dentro de la red de la bodega
make test                      # pytest tests/unit en .venv
make down STACK=multi
```

Sin `STACK`, los targets siguen siendo el Compose raíz (una bodega, `docker compose up`).

### Puertos

| Servicio | Puerto en el host | Observación |
| --- | --- | --- |
| Central | 8004 | Compose central |
| WH-001 | 8101 (`WH001_PORT`) | API directa |
| WH-002 | 8080 (`NGINX_PORT`) | Por nginx; la API no publica puerto para permitir `--scale` |
| WH-003 | 8103 (`WH003_PORT`) | API directa |
| PostgreSQL / Redis | ninguno | Solo accesibles dentro de la red de su bodega |

El issue pide 8000/8001/8002/8003. Se mantuvieron 8004/8101/8080/8103 porque `scripts/demo.sh`, `scripts/smoke.sh`, las pruebas de caos, el despliegue de AWS y `docs/demo.md` ya dependen de ellos; el esquema del issue se obtiene con `WH001_PORT=8001 WH003_PORT=8003 NGINX_PORT=8002` (S-04 publica el balanceador en 8002 con el perfil `lb`).

### Profiles

| Profile | Dónde | Qué levanta |
| --- | --- | --- |
| (ninguno) | `compose.distributed.yml` | 3 bodegas, RabbitMQ y nginx de WH-002 |
| `storage` | `docker-compose.yaml` | MinIO y buckets (F8) |
| `iot` | `docker-compose.yaml` | Mosquitto, ingestión y simulador (F10) |
| `load` | `docker-compose.yaml`, `compose.central.yml` | Locust |
| `obs` | `compose.obs.yml` | Prometheus, Grafana y exporters |
| `lb` | `compose.distributed.yml` (S-04) | 3 réplicas de WH-002 detrás de nginx |

`docker compose up` sin perfiles sigue igual que antes. Con el Makefile: `make up STACK=multi PROFILES="obs"`.

## Demo de aislamiento

Los nombres reales de servicio usan guion bajo (`wh002_api`, `wh002_db`), no `wh-002-api`.

```sh
docker compose -p warehouses-demo -f infrastructure/compose/compose.distributed.yml stop wh002_api wh002_db
curl -H 'X-API-Key: dev-api-key' localhost:8101/inventory/P-001   # WH-001 -> 200
curl -H 'X-API-Key: dev-api-key' localhost:8103/inventory/P-001   # WH-003 -> 200
curl -i -H 'X-API-Key: dev-api-key' localhost:8080/inventory/P-001 # WH-002 -> 504 (nginx sin upstream)
```

Resultado de la corrida ([`aislamiento-demo.txt`](../evidencias/fase-4/aislamiento-demo.txt)): con WH-002 detenida, WH-001 y WH-003 responden 200 y WH-002 responde 504; tras `docker compose start wh002_db wh002_api` las tres vuelven a 200.

## Cierre de la fase

- `docker compose ps` con las tres bodegas sanas, límites de memoria, inventario de `P-001` por bodega (100/20/55), 10 productos por bodega y bases sin puerto: [`s03-multibodega.txt`](../evidencias/fase-4/s03-multibodega.txt). Evidencia previa: [`contenedores.txt`](../evidencias/fase-4/contenedores.txt) y [`aislamiento-datos.txt`](../evidencias/fase-4/aislamiento-datos.txt) (un producto creado en WH-001 no existe en WH-002 ni WH-003).
- Carga por bodega con el `locustfile.py` de J-06 (`ReadSameSku`, 20 s, sin caídas), con `make load STACK=multi`:

  | Bodega | Usuarios | Peticiones | Fallos | Req/s | p50 | p95 |
  | --- | --- | --- | --- | --- | --- | --- |
  | WH-001 | 50 | 29 764 | 0 | 1 565 | 3 ms | 25 ms |
  | WH-003 | 20 | 13 860 | 0 | 729 | 1 ms | 4 ms |

  CSV: [`load-wh001_stats.csv`](../evidencias/fase-4/load-wh001_stats.csv), [`load-wh003_stats.csv`](../evidencias/fase-4/load-wh003_stats.csv). Son corridas cortas de humo, no la carga de la F11 (ver [fase 11](fase-11.md)). La relación 50/800/20 usuarios del issue queda parametrizable con `USERS=`; no se ejecutó a escala completa.

## Decisiones

| Decisión | Elegido | Por qué |
| --- | --- | --- |
| Base de datos | Una PostgreSQL por bodega ([ADR-0007](../adr/0007-una-base-por-bodega.md)) | La caída de una base no afecta a las otras bodegas |
| Configuración por bodega | `wh-00X.env` con `env_file` | Un solo lugar para identidad y clave de la bodega; el Compose queda sin literales |
| Puertos del host | Se conservan 8004/8101/8080/8103 y se hacen configurables | Demo, smoke, caos y AWS ya los usan; la variable permite el esquema 8001-8003 |
| Nombres de servicio | `wh00X_api` (guion bajo) | Los usan los scripts de caos, F11 y la central (`WAREHOUSE_URLS`) |
| `mem_limit` | Valores holgados sobre el uso medido en F11 | Acotar cada contenedor sin provocar OOM bajo carga |
| Makefile | `STACK=single|multi` | No rompe `make up` existente y permite operar las 3 bodegas |
| Clave de API | Dentro de cada `wh-00X.env` | La central sigue leyendo `API_KEY` del entorno (`dev-api-key`); si se cambia una, hay que cambiar la otra |

## Preguntas del profesor

- **¿Qué pasa si cae una bodega?** Solo falla su propio dominio (API, base, Redis). Las demás siguen sirviendo porque no comparten base ni red de datos; solo RabbitMQ es común y las bodegas publican mediante outbox, así que toleran su caída (F3).
- **¿Por qué una base por bodega y no una compartida?** Aislamiento de fallos y de capacidad; el coste es más instancias que operar y la necesidad de proyección o Saga para consultas y transferencias entre bodegas ([ADR-0007](../adr/0007-una-base-por-bodega.md), [ADR-0012](../adr/0012-proyeccion-cqrs.md), [ADR-0013](../adr/0013-saga-orquestada.md)).
- **¿Cómo se distingue una bodega de otra si usan la misma imagen?** Por `WAREHOUSE_ID` (en `wh-00X.env`), que selecciona el seed y se devuelve en cada respuesta.
- **¿Cómo se limitan los recursos?** `mem_limit` por contenedor; los valores se pueden verificar con `docker inspect` o `docker stats`.

## Evidencia

- [`s03-multibodega.txt`](../evidencias/fase-4/s03-multibodega.txt): `docker compose ps`, `mem_limit`, curl por bodega, bases sin puerto.
- [`aislamiento-demo.txt`](../evidencias/fase-4/aislamiento-demo.txt): demo de aislamiento (stop, curl, start).
- [`aislamiento-datos.txt`](../evidencias/fase-4/aislamiento-datos.txt) y [`contenedores.txt`](../evidencias/fase-4/contenedores.txt): evidencia previa de la fase.
- `load-wh001_stats.csv`, `load-wh003_stats.csv`: carga por bodega con Locust.

Nota: la evidencia de S-03 se generó en el proyecto `s03` con los puertos remapeados (`WH001_PORT=28101`, `WH003_PORT=28103`, `NGINX_PORT=28002`) porque otro stack local ocupaba los puertos por defecto. La central (8004) no se levantó en esa corrida.
