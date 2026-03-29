"""One-time script to generate LLM search keys and per-document chunk keys for all existing products."""

import asyncio
import sys

sys.path.insert(0, "/app")

from app.database import async_session
from app.ingestion.product_keys_extractor import (
    aggregate_chunk_entities,
    generate_product_keys_async,
)
from sqlalchemy import text


async def main():
    # --- LLM keys (product-level, document_id=NULL) ---
    async with async_session() as s:
        rows = (await s.execute(text(
            "SELECT id, name, manufacturer, model, category FROM products ORDER BY id"
        ))).mappings().all()
        print(f"Products: {len(rows)}")

        for r in rows:
            existing = (await s.execute(text(
                "SELECT 1 FROM product_search_keys WHERE product_id = :pid AND source = 'llm' LIMIT 1"
            ), {"pid": r["id"]})).first()

            if existing:
                print(f"  {r['name']}: already has LLM keys, skipping")
                continue

            result = await generate_product_keys_async(
                r["name"], r["manufacturer"], r["model"], r["category"],
            )
            if result.keys:
                await s.execute(text(
                    "DELETE FROM product_search_keys "
                    "WHERE product_id = :pid AND source = 'llm' AND document_id IS NULL"
                ), {"pid": r["id"]})
                seen = set()
                for key in result.keys:
                    key_lower = key.strip().lower()
                    if key_lower in seen or not key.strip():
                        continue
                    seen.add(key_lower)
                    await s.execute(text(
                        "INSERT INTO product_search_keys (product_id, document_id, key, source) "
                        "VALUES (:pid, NULL, :key, 'llm')"
                    ), {"pid": r["id"], "key": key.strip()})
                await s.commit()
            print(
                f"  {r['name']}: {len(result.keys)} keys, "
                f"{result.usage.prompt_tokens}+{result.usage.completion_tokens} tokens, "
                f"{result.usage.extract_ms}ms"
            )

    # --- Chunk entity keys (per-document) ---
    async with async_session() as s:
        docs = (await s.execute(text(
            "SELECT d.id AS doc_id, d.product_id "
            "FROM documents d WHERE d.status = 'ready' ORDER BY d.id"
        ))).mappings().all()
        print(f"\nDocuments to process for chunk keys: {len(docs)}")

        for doc_row in docs:
            doc_id = doc_row["doc_id"]
            pid = doc_row["product_id"]

            await s.execute(text(
                "DELETE FROM product_search_keys WHERE document_id = :did AND source = 'chunk'"
            ), {"did": doc_id})

            chunks = (await s.execute(text(
                "SELECT entities FROM chunks WHERE document_id = :did"
            ), {"did": doc_id})).scalars().all()

            chunk_meta_dicts = [{"entities": e} for e in chunks if e]
            keys = aggregate_chunk_entities(chunk_meta_dicts)

            for key in keys:
                await s.execute(text(
                    "INSERT INTO product_search_keys (product_id, document_id, key, source) "
                    "VALUES (:pid, :did, :key, 'chunk') "
                    "ON CONFLICT (product_id, document_id, key) DO NOTHING"
                ), {"pid": pid, "did": doc_id, "key": key})

            await s.commit()
            if keys:
                print(f"  Document {doc_id} (product {pid}): {len(keys)} chunk keys")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
