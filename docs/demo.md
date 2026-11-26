# Guion de demostración

Guion de 10 a 15 minutos. Cada paso es un subcomando de [`scripts/demo.sh`](../scripts/demo.sh), así lo que se muestra es lo que se ensayó. Se ensayó completo en local el 26 de noviembre de 2026 ([salida](evidencias/fase-12/ensayo-demo-local.txt)); los pasos que no necesitan Docker (movimiento, caché, eventos, vista global, transferencia, compensación y humo) se corrieron además contra AWS ([salida](evidencias/fase-9/demo-en-aws.txt)).

## Índice

- Preparación del entorno
- Escenarios de demostración
- Pruebas de funcionamiento
- Simulación de fallos
- Evidencias

## Preparación del entorno

### Local (Compose)

```bash
docker compose -p warehouses-demo \
  -f infrastructure/compose/compose.distributed.yml \
  -f infrastructure/compose/compose.central.yml \
  -f infrastructure/compose/compose.obs.yml --profile obs up -d --build
```

Tarda ~1 minuto en quedar sano. Quedan: WH-001 en el 8101, WH-002 detrás de nginx en el 8080, WH-003 en el 8103, la central en el 8004, RabbitMQ en el 15672 y Grafana en <http://localhost:3000> (`admin` / `admin`). Las claves por defecto son `dev-api-key` y `dev-central-key`.

Antes de empezar, `scripts/demo.sh salud` debe terminar con «Todo en orden».

### AWS

Sigue el runbook de [aws.md](aws.md#runbook): `terraform apply -target` de ECR y S3, `scripts/push-ecr.sh`, `scripts/aws-bundle.sh`, `terraform apply` y `scripts/smoke.sh <ip>`. Para correr el guion contra la EC2:

```bash
export HOST=<ec2_public_ip> API_KEY=... CENTRAL_API_KEY=... PORT_WH2=8102
scripts/demo.sh salud
```

En AWS no hay Grafana ni acceso a la instancia: los pasos `caos`, `bodega-caida` y `carga` son solo locales. Al terminar la sesión: `terraform destroy`.

## Escenarios de demostración

| Min | Qué se muestra | Comando | Qué decir |
| --- | --- | --- | --- |
| 0 | Plataforma sana | `scripts/demo.sh salud` | Tres bodegas con su propia base y Redis, y la central. La transferencia del final prueba la Saga. |
| 1 | Movimiento de inventario | `scripts/demo.sh movimiento` | Una entrada en WH-001 sube la cantidad y la versión. El `X-Correlation-ID` viaja con el movimiento. |
| 2 | Caché | `scripts/demo.sh cache` | Tras escribir, la primera lectura es `MISS` (la caché se invalidó) y la segunda `HIT`. |
| 3 | Evento en RabbitMQ | `scripts/demo.sh rabbit` | El movimiento salió por el outbox transaccional a RabbitMQ. Abrir <http://localhost:15672> y mostrar las colas. |
| 4 | Vista global | `scripts/demo.sh global` | La central proyecta las tres bodegas a partir de los eventos; muestra la versión de cada una. |
| 5 | Transferencia | `scripts/demo.sh transferencia` | La Saga mueve 10 unidades de WH-001 a WH-002 sin transacción global: reserva, envío, recepción. Cada transición queda en el historial. |
| 6 | Fallo provocado (compensación) | `scripts/demo.sh compensacion` | El SKU solo existe en el origen: el destino lo rechaza y la Saga compensa y devuelve el stock (`CANCELLED`, `SKU_NOT_FOUND`). |
| 7 | Fallo provocado (caída del worker) | `scripts/demo.sh caos` | El worker de WH-001 cae después del commit; el mensaje se reentrega y se detecta como duplicado: el stock baja una sola vez (80 → 75). |
| 8 | Una bodega caída | `scripts/demo.sh bodega-caida` | WH-001 y WH-003 siguen respondiendo; la central marca a WH-002 como `stale` a los 90 s sin latido. El paso espera 95 s: se puede narrar el siguiente tema mientras tanto. |
| 10 | Batch → S3 → Lambda | `scripts/demo.sh batch` | El reporte diario lee las bodegas por API, escribe en S3 y registra la corrida. En AWS la Lambda valida el objeto, escribe `metadata/` y registra en la central; el `correlation-id` aparece en CloudWatch. |
| 12 | Grafana | `scripts/demo.sh carga` | Con 100 usuarios sobre WH-001, mostrar en vivo los dashboards APIs, Redis, RabbitMQ, Workers y Saga. |
| 14 | IoT | — | No hay servicio IoT en el repositorio: la fase 12 está sin documentar y no existe código de IoT. No se puede demostrar. |

Los minutos son orientativos; el ensayo local completo tardó unos 3,5 minutos de ejecución (101 s son la caída de bodega con su espera de 95 s) más la narración.

## Pruebas de funcionamiento

- **Humo:** `scripts/demo.sh salud` (12 comprobaciones: salud y base de cada bodega, lectura de inventario, la central, la vista global y una transferencia completa).
- **Seguir una operación por su `correlation_id`:** después del paso 5,

  ```bash
  docker compose -p warehouses-demo -f infrastructure/compose/compose.distributed.yml \
    -f infrastructure/compose/compose.central.yml logs --no-color | grep COR-DEMO-t- | cut -d'|' -f2- | jq -c '{service, event, status}'
  ```

  muestra la API central, los workers de las bodegas y la transición de la Saga con el mismo identificador (ver también [observability.md](observability.md)).
- **Pruebas automáticas:** `pytest tests/unit` y, con la base y RabbitMQ arriba, `pytest tests/integration`.

## Simulación de fallos

| Fallo | Cómo se provoca | Qué debe verse |
| --- | --- | --- |
| Rechazo en destino | `scripts/demo.sh compensacion` | `CANCELLED` con `SKU_NOT_FOUND` y el stock de origen intacto |
| Worker cae tras el commit | `scripts/demo.sh caos` (`CHAOS_FAIL_STEP=SHIP_TRANSFER:after_commit`) | `chaos_fail_injected` y `command_duplicate` en el log; el stock baja una vez |
| Bodega caída | `scripts/demo.sh bodega-caida` | Las otras dos responden; la vista global marca a WH-002 como `stale` |
| Redis caído | `docker compose -p warehouses-demo -f infrastructure/compose/compose.distributed.yml stop wh001_redis` | Las lecturas siguen respondiendo desde PostgreSQL (`X-Cache: BYPASS`); ver [load-testing.md](load-testing.md) |
| RabbitMQ caído | `... stop rabbitmq` | Los movimientos se aceptan y los eventos quedan en el outbox hasta que vuelve; ver [load-testing.md](load-testing.md) |

## Evidencias

| Qué | Dónde |
| --- | --- |
| Ensayo local de punta a punta, con duración de cada paso | [`evidencias/fase-12/ensayo-demo-local.txt`](evidencias/fase-12/ensayo-demo-local.txt) |
| Demo contra AWS (movimiento, caché, evento, vista global, transferencia y compensación) | [`evidencias/fase-9/demo-en-aws.txt`](evidencias/fase-9/demo-en-aws.txt) |
| Despliegue, humo, S3, Lambda y CloudWatch | [aws.md](aws.md) y [`evidencias/fase-9/`](evidencias/fase-9/) |
| Carga y dashboards | [`evidencias/fase-11/`](evidencias/fase-11/README.md) |

## Problemas conocidos al ensayar

- **Los workers `*_cache_invalidation_worker` se reinician en bucle** con la caché en modo `sync` (el valor por defecto): el proceso termina con código 0 y Compose lo vuelve a levantar. No afecta a la demo.
- **La cola `central.audit` acumula mensajes sin consumidor** en este Compose: el worker de auditoría solo está en el Compose raíz.
- **Si se aplica una carga fuerte a WH-002** (cientos de usuarios), sus réplicas pueden atascarse y no se recuperan solas; recrear `wh002_api` y `nginx` ([fase 11](evidencias/fase-11/README.md)). No ocurre con las cargas de esta demo.
- **IoT** no tiene implementación en el repositorio.
