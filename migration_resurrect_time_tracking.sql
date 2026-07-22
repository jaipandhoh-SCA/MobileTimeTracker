-- Migration: Resurrect time-tracking tables and columns
-- Type: ADDITIVE (CREATE TABLE, ADD COLUMN) — no destructive operations
-- Date: 2026-07-22
--
-- This migration recreates the time_entries and active_clocks tables
-- and re-adds hourly_rate columns that were dropped in Phase A.
-- All tables start empty (old data is unrecoverable).

BEGIN;

-- Re-create time_entries table
CREATE TABLE IF NOT EXISTS time_entries (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id),
    client_id INTEGER REFERENCES clients(id),
    date DATE NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    duration_hours NUMERIC(5, 2),
    work_description TEXT NOT NULL,
    is_manual BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_date ON time_entries(user_id, date);
CREATE INDEX IF NOT EXISTS idx_client_date ON time_entries(client_id, date);

-- Re-create active_clocks table
CREATE TABLE IF NOT EXISTS active_clocks (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL UNIQUE REFERENCES users(id),
    start_time TIMESTAMP NOT NULL,
    break_15_taken BOOLEAN DEFAULT FALSE,
    lunch_taken BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Re-add hourly_rate to users (if not present)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'hourly_rate'
    ) THEN
        ALTER TABLE users ADD COLUMN hourly_rate NUMERIC(8, 2) DEFAULT 0;
    END IF;
END $$;

-- Re-add hourly_rate to authorized_users (if not present)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'authorized_users' AND column_name = 'hourly_rate'
    ) THEN
        ALTER TABLE authorized_users ADD COLUMN hourly_rate NUMERIC(8, 2) DEFAULT 0;
    END IF;
END $$;

COMMIT;
