
CREATE TABLE IF NOT EXISTS batch_runs (
    report_date DATE PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    s3_key TEXT,
    error_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 1
        CHECK (attempt_count > 0)
);
