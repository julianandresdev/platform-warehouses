# ADR-0016 — Prometheus y Grafana para observabilidad

## Estado

Propuesto. La instrumentación de la proyección existe. Santiago debe validar el stack completo de S-07.

## Contexto y alternativas

Los logs enlazan una operación concreta mediante su identificador de correlación. Los resúmenes de Locust describen el resultado del cliente. Para identificar dónde se satura el sistema también necesitamos series temporales por componente.

## Decisión

Usar Prometheus para recopilar métricas de API, Redis, PostgreSQL, RabbitMQ y workers. Usar Grafana para correlacionar latencia, errores, rendimiento, colas y retraso de la proyección durante las corridas. Conservar los logs para reconstruir transferencias individuales. Reservar el identificador de correlación para los logs y mantener acotadas las etiquetas de las métricas.

## Consecuencias y validación

La instrumentación añade almacenamiento y puntos de monitoreo. El [worker central](../../services/central/app/workers/main.py) expone `projection_lag_seconds` y la [Fase 7](../fases/fase-7.md) registra su medición local. Falta evidencia de exporters, aprovisionamiento y dashboards con datos en vivo durante una corrida de carga, según el [issue S-07](https://github.com/julianandresdev/platform-warehouses/issues/28).
