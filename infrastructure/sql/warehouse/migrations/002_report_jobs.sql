CREATE TABLE IF NOT EXISTS report_jobs (
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

CREATE INDEX IF NOT EXISTS ix_report_jobs_created_at
    ON report_jobs (created_at DESC);
