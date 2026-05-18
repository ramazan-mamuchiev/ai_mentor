-- Migration: Add code_skeleton_translations JSONB column to api_lifecycles
-- Caches LLM-converted code skeletons for non-Python languages (C#, cURL, etc.)

BEGIN;

ALTER TABLE api_lifecycles
    ADD COLUMN IF NOT EXISTS code_skeleton_translations JSONB;

COMMIT;
