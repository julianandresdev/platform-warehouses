-- Esquema de la base de una bodega. Es la FUENTE DE VERDAD: la API ya no crea
-- tablas (no hay create_all). Los cambios posteriores van en migrations/NNN_*.sql.
-- Se ejecuta una sola vez, al crear el volumen de PostgreSQL (ver init.sh).

CREATE TYPE movement_type AS ENUM ('RECEIPT', 'SHIPMENT', 'ADJUSTMENT');

CREATE TABLE products (
    id          SERIAL       PRIMARY KEY,
    sku         VARCHAR(100) NOT NULL,
    name        VARCHAR(200) NOT NULL,
    description TEXT,
    category    VARCHAR(100),
    unit        VARCHAR(50)  NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at  TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_products_sku UNIQUE (sku)
);

CREATE TABLE inventory (
    id                SERIAL      PRIMARY KEY,
    -- RESTRICT: no se puede borrar un producto que tenga inventario.
    product_id        INTEGER     NOT NULL REFERENCES products (id) ON DELETE RESTRICT,
    warehouse_id      VARCHAR(20) NOT NULL,
    quantity          INTEGER     NOT NULL DEFAULT 0,
    reserved_quantity INTEGER     NOT NULL DEFAULT 0,
    -- Sube en 1 con cada cambio; los consumidores de eventos la usan para ignorar
    -- mensajes viejos o duplicados (Fase 7).
    version           INTEGER     NOT NULL DEFAULT 0,
    updated_at        TIMESTAMP   NOT NULL DEFAULT now(),
    -- Sin esta restriccion, el FOR UPDATE no protege la primera entrada de un
    -- producto (todavia no hay fila que bloquear) y dos entradas simultaneas
    -- crearian dos filas.
    CONSTRAINT uq_inventory_product_warehouse UNIQUE (product_id, warehouse_id),
    CONSTRAINT ck_inventory_quantity_non_negative CHECK (quantity >= 0),
    CONSTRAINT ck_inventory_reserved_valid
        CHECK (reserved_quantity >= 0 AND reserved_quantity <= quantity)
);

CREATE TABLE inventory_movements (
    id           SERIAL        PRIMARY KEY,
    -- RESTRICT: no se puede borrar un producto con historial de movimientos.
    product_id   INTEGER       NOT NULL REFERENCES products (id) ON DELETE RESTRICT,
    warehouse_id VARCHAR(20)   NOT NULL,
    type         movement_type NOT NULL,
    -- RECEIPT y SHIPMENT guardan la cantidad movida (positiva). ADJUSTMENT guarda
    -- la diferencia contra el inventario (puede ser negativa); nunca cero.
    quantity     INTEGER       NOT NULL,
    reference    VARCHAR(255),
    created_at   TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT ck_movements_quantity_not_zero CHECK (quantity <> 0)
);

CREATE TABLE report_jobs (
    job_id      UUID PRIMARY KEY,
    status      VARCHAR(20) NOT NULL,
    params      JSONB NOT NULL,
    result      JSONB,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT ck_report_jobs_status
        CHECK (status IN ('PROCESSING', 'DONE', 'FAILED'))
);

CREATE INDEX ix_report_jobs_created_at ON report_jobs (created_at DESC);

CREATE INDEX ix_inventory_movements_lookup
    ON inventory_movements (product_id, warehouse_id, created_at DESC);
