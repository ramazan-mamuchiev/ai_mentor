-- Migration 009: Recalculate tsv with setweight for all existing chunks.
--
-- The chunks_tsv_trigger() function was updated to use setweight (A for heading,
-- B for entities/doc_type, C for content). Existing rows need their tsv column
-- recalculated with the new weights.
--
-- Uses batches of 1000 rows to avoid long locks on the GIN index.
-- Progress is logged via RAISE NOTICE.

DO $$
DECLARE
    batch_size INT := 1000;
    total_rows INT;
    last_id BIGINT := 0;
    batch_ids BIGINT[];
    updated_count INT := 0;
BEGIN
    SELECT count(*) INTO total_rows FROM chunks;
    RAISE NOTICE 'TSV weight backfill: % total chunks', total_rows;

    IF total_rows = 0 THEN
        RAISE NOTICE 'No chunks to update, exiting';
        RETURN;
    END IF;

    LOOP
        SELECT array_agg(id) INTO batch_ids
        FROM (
            SELECT id FROM chunks
            WHERE id > last_id
            ORDER BY id
            LIMIT batch_size
        ) sub;

        EXIT WHEN batch_ids IS NULL OR array_length(batch_ids, 1) IS NULL;

        UPDATE chunks
        SET content_clean = content_clean
        WHERE id = ANY(batch_ids);

        last_id := batch_ids[array_upper(batch_ids, 1)];
        updated_count := updated_count + array_length(batch_ids, 1);
        RAISE NOTICE 'TSV weight backfill: % / % chunks processed (last_id=%)',
            updated_count, total_rows, last_id;
    END LOOP;

    RAISE NOTICE 'TSV weight backfill complete: % chunks updated', updated_count;
END $$;
