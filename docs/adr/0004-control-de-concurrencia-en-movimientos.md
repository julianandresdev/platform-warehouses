# ADR-0004: Control de concurrencia en los movimientos de inventario

- Estado: aceptado
- Fecha: 2026-11-22
- Autor: Julian

## Contexto

Varias peticiones pueden modificar el mismo inventario a la vez (más aún con réplicas de la API). Dos casos concretos:

1. **Dos salidas de 6 unidades sobre un stock de 10.** Si ambas leen 10 antes de que alguna escriba, las dos pasan y el stock queda en -2 (o en 4, con una actualización perdida).
2. **Dos primeras entradas de un producto nuevo.** Todavía no hay fila de inventario, así que `SELECT ... FOR UPDATE` no bloquea nada y cada petición crea la suya.

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **Bloqueo pesimista: `INSERT ... ON CONFLICT DO NOTHING` + `SELECT ... FOR UPDATE`** | Correcto con cualquier número de réplicas; simple de razonar; el estado se valida con la fila ya bloqueada | Las peticiones sobre el mismo producto se serializan |
| Bloqueo optimista (`version` y reintentos) | No retiene bloqueos | Hay que reintentar y devolver errores 409 de versión al cliente |
| Aislamiento `SERIALIZABLE` | La base lo garantiza | Fallos de serialización frecuentes que hay que reintentar; más costoso |
| Lock en memoria de la API | Muy fácil | No funciona con más de una réplica |

## Decisión

Dentro de una sola transacción:

1. `INSERT ... ON CONFLICT (product_id, warehouse_id) DO NOTHING` garantiza que exista la fila. Se apoya en la restricción `UNIQUE (product_id, warehouse_id)` y, si otra transacción la está creando, espera a que termine.
2. `SELECT ... FOR UPDATE` bloquea la fila.
3. Con la fila bloqueada se valida la regla: una salida compara contra lo **disponible** (`quantity - reserved_quantity`); un `ADJUSTMENT` no puede quedar bajo lo reservado.
4. Se actualizan `quantity` y `version` y se inserta el movimiento.
5. Si algo falla, se revierte todo, incluida la fila creada en el paso 1.

## Consecuencias

- Dos salidas de 6 sobre stock 10 dan exactamente un 201 y un 409, y el stock final es 4.
- Cuatro primeras entradas simultáneas dejan una sola fila de inventario con la suma correcta.
- Una salida sobre un producto sin inventario responde 409 y no deja fila huérfana.
- La concurrencia sobre un mismo producto se serializa: es un costo aceptable porque los movimientos son cortos y el bloqueo es por fila, no por tabla.
- Los `CHECK` de la base (ADR-0003) siguen protegiendo si alguien escribe sin pasar por la API.
- Cuando se agregue el outbox (Fase 3), el evento se inserta en esta misma transacción.
