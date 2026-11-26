# ADR-0007 — Una base PostgreSQL por bodega

## Estado

Implementado en Docker Compose. Pendiente de revisión de Santiago.

## Contexto

Cada bodega registra sus movimientos y mantiene su inventario. Una caída
en la persistencia de una bodega debe limitarse a sus propias operaciones.

## Alternativas consideradas

Una instancia compartida con inventario separado por `warehouse_id`
simplifica la administración y las consultas cruzadas. También comparte
capacidad y dominio de fallo entre bodegas. Una instancia por bodega
permite administrar y dimensionar cada base por separado.

## Decisión

Asignar PostgreSQL y volumen propios a WH-001, WH-002 y WH-003. Las
réplicas de API de cada bodega comparten la base de esa bodega. La central
mantiene su proyección a partir de eventos, según el
[ADR-0012](0012-proyeccion-cqrs.md).

## Consecuencias

El almacenamiento de cada bodega puede escalar de forma independiente.
Hay más instancias que respaldar, migrar y monitorear. Las consultas
globales necesitan una proyección o llamadas a las APIs. Las
transferencias entre bases se coordinan con el [ADR-0013](0013-saga-orquestada.md).

## Validación

Ver el [Compose distribuido](../../infrastructure/compose/compose.distributed.yml)
y la [evidencia de aislamiento de datos](../evidencias/fase-4/aislamiento-datos.txt).
