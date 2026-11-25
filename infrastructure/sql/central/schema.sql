-- Base de datos de la plataforma central
-- Fase 7: CQRS y modelo de lectura

-- Inventario consolidado de todas las bodegas
CREATE TABLE global_inventory (
    sku               VARCHAR(100) NOT NULL,
    warehouse_id      VARCHAR(20) NOT NULL,
    quantity          INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    version           INTEGER NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (sku, warehouse_id),

    CONSTRAINT ck_global_quantity
        CHECK (quantity >= 0),

    CONSTRAINT ck_global_reserved
        CHECK (
            reserved_quantity >= 0
            AND reserved_quantity <= quantity
        ),

    CONSTRAINT ck_global_version
        CHECK (version >= 0)
);

-- Estado de conexión y actividad de cada bodega
CREATE TABLE warehouse_status (
    warehouse_id   VARCHAR(20) PRIMARY KEY,
    last_seen_at   TIMESTAMPTZ,
    last_event_at  TIMESTAMPTZ
);

-- =========================================================
-- Fase 6: Transferencias distribuidas mediante Saga
-- =========================================================

-- Transferencias coordinadas por la plataforma central
CREATE TABLE transfers (
    id                       UUID PRIMARY KEY,
    idempotency_key          VARCHAR(255) NOT NULL UNIQUE,
    source_warehouse_id      VARCHAR(20) NOT NULL,
    destination_warehouse_id VARCHAR(20) NOT NULL,
    sku                      VARCHAR(100) NOT NULL,
    quantity                 INTEGER NOT NULL,
    status                   VARCHAR(40) NOT NULL DEFAULT 'REQUESTED',
    reason                   TEXT,
    deadline                 TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at             TIMESTAMPTZ,

    CONSTRAINT ck_transfer_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_transfer_different_warehouses
        CHECK (source_warehouse_id <> destination_warehouse_id)
);

-- Historial de cambios de estado de cada transferencia
CREATE TABLE transfer_history (
    id              BIGSERIAL PRIMARY KEY,
    transfer_id     UUID NOT NULL
                    REFERENCES transfers(id) ON DELETE CASCADE,
    previous_status VARCHAR(40),
    new_status      VARCHAR(40) NOT NULL,
    reason          TEXT,
    correlation_id  VARCHAR(100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_transfer_history_transfer
    ON transfer_history (transfer_id, created_at);

-- =========================================================
-- Mensajería: Outbox e idempotencia
-- =========================================================

-- Eventos y comandos pendientes de publicación en RabbitMQ
CREATE TABLE outbox (
    id           BIGSERIAL PRIMARY KEY,
    event_id     UUID NOT NULL UNIQUE,
    exchange     TEXT NOT NULL,
    routing_key  TEXT NOT NULL,
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    attempts     INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT ck_outbox_attempts
        CHECK (attempts >= 0)
);

CREATE INDEX ix_central_outbox_pending
    ON outbox (id)
    WHERE published_at IS NULL;

-- Registro de mensajes procesados para evitar duplicados
CREATE TABLE processed_messages (
    message_id   UUID NOT NULL,
    consumer     VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (message_id, consumer)
);

-- =========================================================
-- Auditoría de eventos
-- =========================================================

CREATE TABLE audit_events (
    event_id       UUID PRIMARY KEY,
    event_type     VARCHAR(100) NOT NULL,
    source         VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(100),
    payload        JSONB NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================
-- Procesamiento Batch y reportes
-- =========================================================

-- Registro de las ejecuciones de trabajos Batch
CREATE TABLE batch_runs (
    run_id      UUID PRIMARY KEY,
    report_date DATE NOT NULL,
    status      VARCHAR(30) NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    objects     JSONB NOT NULL DEFAULT '[]'::jsonb
);

-- Registro de reportes generados y almacenados en S3
CREATE TABLE reports (
    id         BIGSERIAL PRIMARY KEY,
    object_key TEXT NOT NULL UNIQUE,
    status     VARCHAR(30) NOT NULL,
    size       BIGINT,
    checksum   VARCHAR(64),
    metadata   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_report_size
        CHECK (size IS NULL OR size >= 0)
);
