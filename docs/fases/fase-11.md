# Fase 11 — Observabilidad y pruebas de carga

## Objetivo

Analizar rendimiento, identificar cuellos de botella
y justificar las decisiones de escalabilidad.

## Escenarios

| Escenario | Estado |
|---|---|
| Redis ON/OFF | Resultados históricos F2 consolidados |
| Una frente a tres réplicas | Resultados históricos F5 consolidados |
| Carga desigual entre bodegas | Pendiente J-09 |
| Carga progresiva | Pendiente J-09 |

## Preguntas de análisis y defensa

### ¿Qué métricas permiten evaluar el rendimiento?

RPS, latencias P50/P95/P99, tasa de errores,
CPU, memoria, hit ratio, mensajes pendientes
y retraso de la proyección central.

### ¿Cómo mejora Redis el rendimiento?

En F2 se observaron 1795.7 RPS con Redis
y 827.4 RPS sin Redis. El P95 pasó de 130 a 52 ms.

Redis reduce las consultas repetitivas a PostgreSQL.

[Evidencia F2](../evidencias/fase-2/resumen.md).

### ¿Qué aporta el escalamiento horizontal?

En F5 el rendimiento pasó de 382.98 RPS con una
réplica a 884.36 RPS con tres réplicas.

Nginx distribuye las solicitudes entre instancias.

[Evidencia F5](../evidencias/fase-5/comparacion-rendimiento.md).

### ¿Cómo identificar un cuello de botella?

Se deben correlacionar latencias, errores, RPS,
CPU y memoria de cada componente.

También debe medirse el generador Locust para distinguir
una saturación del sistema de una saturación del cliente.

### ¿Cómo seguir una operación distribuida?

Mediante logs estructurados y correlation_id,
relacionando la solicitud inicial con los eventos,
workers y operaciones posteriores.

Las evidencias de F10 contienen identificadores
de correlación de movimientos de inventario.

[Evidencia](../evidencias/fase-10/worker-outbox-publicado.txt).

La trazabilidad de una transferencia Saga completa
queda pendiente de incorporación.

### ¿Cómo escalar a 100 bodegas con cargas diferentes?

Escalar independientemente cada bodega según demanda,
utilizar Redis para reducir consultas repetitivas,
desacoplar operaciones mediante RabbitMQ y Outbox,
y consultar el inventario global mediante CQRS.

Utilizar Saga para coordinar transferencias y
Prometheus/Grafana para identificar saturación.

Los resultados F2 y F5 respaldan estas decisiones,
pero no demuestran capacidad para 100 bodegas.
La justificación cuantitativa se completará con J-09.

## Estado

- [x] Consolidación de resultados históricos F2 y F5.
- [x] Informe estructurado por escenarios.
- [x] Propuesta de escalabilidad.
- [ ] Resultados de carga desigual.
- [ ] Resultados de carga progresiva.
- [ ] CSV de Locust.
- [ ] Capturas de Grafana y consumo de recursos.
- [ ] Trazabilidad de transferencia completa.
- [ ] Revisión final.

Las preguntas anteriores son una síntesis técnica
de preparación para la defensa.

[Informe de rendimiento](../load-testing.md).
