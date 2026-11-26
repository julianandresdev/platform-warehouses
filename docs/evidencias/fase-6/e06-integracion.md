# E-06 — Validación de integración con J-07

Fecha: 25 de noviembre de 2026 (Colombia).
Los timestamps del sistema corresponden al 26 de noviembre UTC.

Entorno: Docker Compose, proyecto aislado e06-saga.
Tres bodegas independientes, PostgreSQL, Redis y RabbitMQ.

## Resultados

| Escenario | Resultado | Estado final |
| --- | --- | --- |
| Transferencia exitosa de 30 unidades | Exitoso | COMPLETED |
| Solicitud de 1000 unidades sin stock suficiente | Exitoso | FAILED |
| Tres repeticiones de la misma solicitud | Exitoso | COMPLETED |
| Rechazo de recepción y devolución de stock | Exitoso | CANCELLED |
| Fallo inducido de envío y liberación | Exitoso | CANCELLED |

Pruebas unitarias de Saga: 46/46 superadas.
Escenarios manuales de integración: 5/5 superados.

## 1. Transferencia exitosa

- Transfer ID: 1f1b77e7-12be-4c04-91db-b2427ef833ff
- Correlation ID: COR-20261126-7e95607b
- SKU: P-001.
- Cantidad: 30.
- Duración: aproximadamente 4.71 segundos.

| Bodega | Antes | Después |
| --- | ---: | ---: |
| WH-001 | 100 | 70 |
| WH-002 | 20 | 50 |
| WH-003 | 55 | 55 |
| Total | 175 | 175 |

Movimientos: RESERVATION, TRANSFER_OUT y TRANSFER_IN.
Siete estados registrados y ninguna reserva pendiente.

## 2. Stock insuficiente

- Transfer ID: 63b0bd7e-ef84-461d-9328-7d86f2cacff2
- Cantidad solicitada: 1000.
- Estado: FAILED.
- Motivo: INSUFFICIENT_STOCK.
- Duración: aproximadamente 0.63 segundos.

No se produjeron movimientos ni cambios de inventario o versiones.

## 3. Idempotencia HTTP

Se repitió tres veces la solicitud del primer escenario
con la misma Idempotency-Key.

Las tres respuestas conservaron el transfer_id original.
El total de transferencias registradas permaneció en dos.
No se duplicaron movimientos ni cambios de inventario.
El historial original conservó sus siete estados.

## 4. Rechazo en destino

- Transfer ID: 3e459e51-9caf-44ee-a744-99d5c1437cee
- SKU: E06-COMP-bc8c6f21.
- Cantidad: 10.
- Estado: CANCELLED.
- Motivo: SKU_NOT_FOUND.
- Duración: aproximadamente 3.48 segundos.

Se creó mediante SQL un producto de prueba exclusivamente
en WH-001, con 40 unidades.

La Saga ejecutó RESERVATION, TRANSFER_OUT y TRANSFER_RETURN.
El inventario final volvió a 40 unidades, con cero reservas
y ningún movimiento en el destino.

## 5. Fallo definitivo de envío

- Transfer ID: 154cd6a9-eb93-4a90-a4c4-553ccdda0231
- Correlation ID: COR-20261126-8bc7a4c7
- SKU: P-001.
- Cantidad: 5.
- Estado: CANCELLED.
- Motivo: NO_ACTIVE_RESERVATION.

Se detuvo temporalmente el consumidor de comandos del origen
y se liberó anticipadamente la reserva usando el handler real.

La central ignoró la confirmación de liberación no solicitada.

Al reactivar el consumidor, la bodega emitió
TRANSFER_SHIP_FAILED. La central pasó de SOURCE_RESERVED
a COMPENSATING y solicitó RELEASE_RESERVATION.

La bodega confirmó RESERVATION_RELEASED de forma idempotente
y la transferencia alcanzó CANCELLED.

Movimientos registrados:
- RESERVATION: 5.
- RESERVATION_RELEASE: 5.

No se registraron TRANSFER_OUT ni TRANSFER_RETURN.

El inventario de P-001 permaneció en 70/50/55 unidades
respectivamente, con cero reservas y 175 unidades totales.

## Limitaciones

Las pruebas se realizaron localmente, no en AWS.
Los fallos de recepción y envío fueron inducidos.
La prueba de fallo de envío incluye una intervención manual
sobre el handler para reproducir la ausencia de reserva.

Las 46 pruebas corresponden exclusivamente al módulo Saga,
no a la totalidad de las pruebas ni de los servicios.

La aprobación, CI y fusión del PR #56 deben verificarse en GitHub.

## Conclusión

La integración E-06/J-07 permitió verificar la coordinación
de transferencias, compensaciones, conservación del inventario
e idempotencia en los cinco escenarios ejecutados.

Evidencia complementaria: [resultados](e06-resultados.txt).
