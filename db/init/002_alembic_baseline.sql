-- Fresh-volume bootstrap only. 001_init.sql owns the historical baseline schema;
-- Alembic revision 0001 is intentionally a marker for that exact schema.
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

INSERT INTO alembic_version (version_num)
VALUES ('0001_initial')
ON CONFLICT (version_num) DO NOTHING;
