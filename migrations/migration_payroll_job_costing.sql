-- Migration: Connect payroll to job costing
-- Additive only — safe to run multiple times (IF NOT EXISTS / existence checks)
-- Run manually via Neon console

-- Add cost_code_id to time_entries if missing
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='time_entries' AND column_name='cost_code_id') THEN
        ALTER TABLE time_entries ADD COLUMN cost_code_id INTEGER REFERENCES cost_codes(id);
    END IF;
END $$;

-- Add approval status to time_entries if missing
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='time_entries' AND column_name='status') THEN
        ALTER TABLE time_entries ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending';
    END IF;
END $$;

-- Add rejection_reason to time_entries if missing
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='time_entries' AND column_name='rejection_reason') THEN
        ALTER TABLE time_entries ADD COLUMN rejection_reason TEXT;
    END IF;
END $$;

-- Add approved_by_user_id to time_entries if missing
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='time_entries' AND column_name='approved_by_user_id') THEN
        ALTER TABLE time_entries ADD COLUMN approved_by_user_id VARCHAR REFERENCES users(id);
    END IF;
END $$;

-- Add approved_at to time_entries if missing
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='time_entries' AND column_name='approved_at') THEN
        ALTER TABLE time_entries ADD COLUMN approved_at TIMESTAMP;
    END IF;
END $$;

-- Add burden_multiplier to users if missing
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='burden_multiplier') THEN
        ALTER TABLE users ADD COLUMN burden_multiplier NUMERIC(5, 4);
    END IF;
END $$;

-- Index for filtering by status + date
CREATE INDEX IF NOT EXISTS idx_te_status ON time_entries (status, date);
