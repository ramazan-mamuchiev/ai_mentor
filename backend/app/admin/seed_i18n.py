"""Seed languages and UI translations from en.json / ru.json.

Called at application startup (lifespan). Uses MD5 hash of JSON content
to skip re-seeding when nothing changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_LOCALES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "src" / "locales"

_SYSTEM_LANGUAGES = [
    {"code": "en", "name_native": "English", "is_default": True, "sort_order": 0},
    {"code": "ru", "name_native": "Русский", "is_default": False, "sort_order": 1},
]


async def seed_i18n(session: AsyncSession) -> None:
    """Seed system languages and UI translation strings."""
    await _seed_languages(session)
    await _seed_ui_translations(session)


async def _seed_languages(session: AsyncSession) -> None:
    for lang in _SYSTEM_LANGUAGES:
        await session.execute(
            text(
                "INSERT INTO languages (code, name_native, is_default, is_active, sort_order, is_system) "
                "VALUES (:code, :name_native, :is_default, TRUE, :sort_order, TRUE) "
                "ON CONFLICT (code) DO UPDATE SET "
                "name_native = EXCLUDED.name_native, "
                "is_default = EXCLUDED.is_default, "
                "sort_order = EXCLUDED.sort_order"
            ),
            lang,
        )
    await session.commit()
    logger.info("Seeded system languages", extra={"count": len(_SYSTEM_LANGUAGES)})


async def _seed_ui_translations(session: AsyncSession) -> None:
    """Load en.json and ru.json, compute combined MD5, skip if unchanged."""
    en_path = _LOCALES_DIR / "en.json"
    ru_path = _LOCALES_DIR / "ru.json"

    if not en_path.exists() or not ru_path.exists():
        logger.warning("Locale files not found, skipping UI translation seed")
        return

    en_data: dict = json.loads(en_path.read_text(encoding="utf-8"))
    ru_data: dict = json.loads(ru_path.read_text(encoding="utf-8"))

    combined = json.dumps({"en": en_data, "ru": ru_data}, sort_keys=True)
    current_hash = hashlib.md5(combined.encode()).hexdigest()

    row = await session.execute(
        text("SELECT value FROM translations WHERE namespace = 'meta' AND key = 'ui_seed_hash' LIMIT 1")
    )
    stored_hash = row.scalar_one_or_none()
    if stored_hash == current_hash:
        logger.info("UI translations unchanged (hash match), skipping seed")
        return

    lang_rows = await session.execute(
        text("SELECT id, code FROM languages WHERE code IN ('en', 'ru')")
    )
    lang_map = {r.code: r.id for r in lang_rows}

    if "en" not in lang_map or "ru" not in lang_map:
        logger.error("System languages en/ru not found — cannot seed translations")
        return

    all_keys = set(en_data.keys()) | set(ru_data.keys())

    rows = []
    for key in sorted(all_keys):
        if key in en_data:
            rows.append({
                "language_id": lang_map["en"],
                "namespace": "ui",
                "key": key,
                "value": en_data[key],
                "is_system": True,
            })
        if key in ru_data:
            rows.append({
                "language_id": lang_map["ru"],
                "namespace": "ui",
                "key": key,
                "value": ru_data[key],
                "is_system": True,
            })

    if rows:
        values_clause = ", ".join(
            f"({r['language_id']}, 'ui', :k{i}, :v{i}, TRUE)"
            for i, r in enumerate(rows)
        )
        params = {}
        for i, r in enumerate(rows):
            params[f"k{i}"] = r["key"]
            params[f"v{i}"] = r["value"]

        batch_size = 500
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            for r in batch:
                await session.execute(
                    text(
                        "INSERT INTO translations (language_id, namespace, key, value, is_system) "
                        "VALUES (:language_id, :namespace, :key, :value, :is_system) "
                        "ON CONFLICT (language_id, namespace, key) DO UPDATE SET "
                        "value = EXCLUDED.value, is_system = EXCLUDED.is_system, "
                        "updated_at = NOW()"
                    ),
                    r,
                )

    meta_lang_id = lang_map["en"]
    await session.execute(
        text(
            "INSERT INTO translations (language_id, namespace, key, value, is_system) "
            "VALUES (:lid, 'meta', 'ui_seed_hash', :hash, TRUE) "
            "ON CONFLICT (language_id, namespace, key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"
        ),
        {"lid": meta_lang_id, "hash": current_hash},
    )

    await session.commit()
    logger.info("Seeded UI translations", extra={"total_rows": len(rows), "hash": current_hash})
