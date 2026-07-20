-- Phase A Migration: Remove time-tracking tables and columns
-- Run against Neon PostgreSQL AFTER backing up the database
-- This permanently deletes all time entry and payroll data
--
-- To back up first:
--   pg_dump "$DATABASE_URL" > backup_before_phase_a.sql

BEGIN;

-- Drop time-tracking tables
DROP TABLE IF EXISTS time_entries;
DROP TABLE IF EXISTS active_clocks;

-- Remove hourly_rate from users
ALTER TABLE users DROP COLUMN IF EXISTS hourly_rate;

-- Remove hourly_rate from authorized_users
ALTER TABLE authorized_users DROP COLUMN IF EXISTS hourly_rate;

COMMIT;
