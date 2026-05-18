-- Migration: rename database ipcodex -> ai_mentor, user ipcodex -> ai_mentor
-- 
-- IMPORTANT: Run this script connected to the "postgres" database (not ipcodex),
-- and ensure no active connections to ipcodex exist.
--
-- Usage:
--   psql -U ipcodex -d postgres -f migrate_ipcodex_to_lexiro.sql
--
-- If running inside Docker:
--   docker compose exec postgres psql -U ipcodex -d postgres -f /tmp/migrate.sql

-- 1. Terminate all connections to ipcodex
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'ipcodex' AND pid <> pg_backend_pid();

-- 2. Rename database
ALTER DATABASE ipcodex RENAME TO ai_mentor;

-- 3. Rename user
ALTER USER ipcodex RENAME TO ai_mentor;

-- 4. Update password to match new defaults
ALTER USER ai_mentor WITH PASSWORD 'ai_mentor_dev';
