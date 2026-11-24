-- F6 (J-07): comandos de la Saga en la bodega.
--
-- 1. processed_messages: registro idempotente de los comandos consumidos. El
--    worker inserta aquí como PRIMER paso de la transacción del comando; si la
--    llave (message_id, consumer) ya existe, el mensaje es un duplicado y se
--    confirma (ack) sin repetir el efecto.
-- 2. Tipos de movimiento de las transferencias. Cada uno guarda la cantidad
--    (positiva) y en `reference` el texto `transfer:<transfer_id>`, que permite
--    saber qué pasos de una transferencia ya se aplicaron en esta bodega.
--
-- ALTER TYPE ... ADD VALUE no puede usarse en la misma transacción que lo crea;
-- init.sh ejecuta cada sentencia en autocommit, así que no se envuelve en BEGIN.

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id   UUID        NOT NULL,
    consumer     TEXT        NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_processed_messages PRIMARY KEY (message_id, consumer)
);

-- Reserva de stock para una transferencia (sube reserved_quantity).
ALTER TYPE movement_type ADD VALUE IF NOT EXISTS 'RESERVATION';
-- Liberación de una reserva que no llegó a despacharse (baja reserved_quantity).
ALTER TYPE movement_type ADD VALUE IF NOT EXISTS 'RESERVATION_RELEASE';
-- Salida de la bodega origen (baja quantity y reserved_quantity).
ALTER TYPE movement_type ADD VALUE IF NOT EXISTS 'TRANSFER_OUT';
-- Entrada en la bodega destino (sube quantity).
ALTER TYPE movement_type ADD VALUE IF NOT EXISTS 'TRANSFER_IN';
-- Compensación en la bodega origen tras un rechazo del destino (sube quantity).
ALTER TYPE movement_type ADD VALUE IF NOT EXISTS 'TRANSFER_RETURN';

CREATE INDEX IF NOT EXISTS ix_inventory_movements_reference
    ON inventory_movements (reference)
    WHERE reference IS NOT NULL;
