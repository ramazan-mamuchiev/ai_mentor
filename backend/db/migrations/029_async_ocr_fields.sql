-- Migration: Add async OCR pipeline fields to documents.
-- ocr_status tracks the background OCR phase: '' | 'pending' | 'processing' | 'complete' | 'failed' | 'skipped'
-- ocr_progress_percent is 0-100 progress for the OCR phase shown in UI.
-- ocr_task_id stores the Celery task ID of the OCR orchestrator.

BEGIN;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_status TEXT NOT NULL DEFAULT '';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_progress_percent INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_task_id TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_image_dicts JSONB;

COMMIT;
