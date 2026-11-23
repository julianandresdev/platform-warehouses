\set ON_ERROR_STOP on

BEGIN;

-- Convertir identificadores antiguos al código de cada bodega.
ALTER TABLE inventory
    ALTER COLUMN warehouse_id TYPE VARCHAR(20)
    USING :'warehouse_id'::VARCHAR(20);

ALTER TABLE inventory_movements
    ALTER COLUMN warehouse_id TYPE VARCHAR(20)
    USING :'warehouse_id'::VARCHAR(20);

-- Agregar control de versiones.
ALTER TABLE inventory
    ADD COLUMN version INTEGER NOT NULL DEFAULT 0;

-- Actualizar el tipo de movimientos.
ALTER TYPE movementtype RENAME TO movement_type;
ALTER TYPE movement_type ADD VALUE 'ADJUSTMENT';

-- Agregar restricciones del esquema oficial.
ALTER TABLE inventory
    ADD CONSTRAINT uq_inventory_product_warehouse
    UNIQUE (product_id, warehouse_id);

ALTER TABLE inventory
    ADD CONSTRAINT ck_inventory_quantity_non_negative
    CHECK (quantity >= 0);

ALTER TABLE inventory
    ADD CONSTRAINT ck_inventory_reserved_valid
    CHECK (reserved_quantity >= 0 AND reserved_quantity <= quantity);

ALTER TABLE inventory_movements
    ADD CONSTRAINT ck_movements_quantity_not_zero
    CHECK (quantity <> 0);

CREATE INDEX ix_inventory_movements_lookup
    ON inventory_movements
    (product_id, warehouse_id, created_at DESC);

COMMIT;
