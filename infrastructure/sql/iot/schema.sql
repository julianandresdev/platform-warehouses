-- Base de datos del pipeline IoT (profile `iot`).

CREATE TABLE sensor_readings (
    event_id UUID PRIMARY KEY,
    warehouse_id VARCHAR(20) NOT NULL,
    sensor_id VARCHAR(100) NOT NULL,
    sensor_type VARCHAR(20) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    sequence_number BIGINT NOT NULL CHECK (sequence_number > 0),
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    out_of_order BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ix_sensor_readings_sensor_sequence
    ON sensor_readings (sensor_id, sequence_number);
CREATE INDEX ix_sensor_readings_ingested_at
    ON sensor_readings (ingested_at);

CREATE TABLE sensor_state (
    sensor_id VARCHAR(100) PRIMARY KEY,
    warehouse_id VARCHAR(20) NOT NULL,
    sensor_type VARCHAR(20) NOT NULL,
    last_sequence BIGINT NOT NULL CHECK (last_sequence > 0),
    last_value DOUBLE PRECISION NOT NULL,
    last_ts TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sensor_ingestion_stats (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    received BIGINT NOT NULL DEFAULT 0,
    stored_unique BIGINT NOT NULL DEFAULT 0,
    duplicates_discarded BIGINT NOT NULL DEFAULT 0,
    out_of_order BIGINT NOT NULL DEFAULT 0
);
INSERT INTO sensor_ingestion_stats (singleton) VALUES (TRUE)
ON CONFLICT DO NOTHING;

CREATE TABLE sensor_processed_messages (
    event_id UUID NOT NULL,
    consumer VARCHAR(50) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, consumer)
);

CREATE TABLE sensor_alert_state (
    sensor_id VARCHAR(100) PRIMARY KEY,
    warehouse_id VARCHAR(20) NOT NULL,
    last_sequence BIGINT NOT NULL DEFAULT 0,
    above_threshold_streak INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sensor_alerts (
    alert_id UUID PRIMARY KEY,
    sensor_id VARCHAR(100) NOT NULL,
    warehouse_id VARCHAR(20) NOT NULL,
    sequence_number BIGINT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_sensor_alerts_pending
    ON sensor_alerts (created_at)
    WHERE published_at IS NULL;
