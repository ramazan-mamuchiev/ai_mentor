"""One-shot migration: map products.category (text) to products.category_id (FK).

Reads current text category values, attempts to match them to product_categories slugs,
and updates the FK. Idempotent — skips products that already have category_id set.

Usage:
    python -m scripts.migrate_product_categories
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings


CATEGORY_MAPPING: dict[str, str] = {
    "camera": "video_surveillance",
    "cameras": "video_surveillance",
    "ip camera": "video_surveillance",
    "ip cameras": "video_surveillance",
    "video": "video_surveillance",
    "video surveillance": "video_surveillance",
    "nvr": "video_surveillance",
    "dvr": "video_surveillance",
    "access control": "access_control",
    "access": "access_control",
    "controller": "access_control",
    "intercom": "intercom",
    "door station": "intercom",
    "alarm": "alarm_intrusion",
    "intrusion": "alarm_intrusion",
    "building automation": "building_automation",
    "bms": "building_automation",
    "software": "software",
    "vms": "software",
    "platform": "software",
    "sdk": "software",
    "protocol": "protocols",
    "protocols": "protocols",
    "onvif": "protocols",
    "isapi": "protocols",
}


def migrate():
    engine = create_engine(settings.database_url_sync)

    with Session(engine) as session:
        cat_rows = session.execute(
            text("SELECT id, slug FROM product_categories")
        ).all()
        slug_to_id = {row.slug: row.id for row in cat_rows}

        if not slug_to_id:
            print("No categories found — run the app first to seed categories.")
            return

        products = session.execute(
            text("SELECT id, category FROM products WHERE category_id IS NULL AND category != ''")
        ).all()

        if not products:
            print("No products need migration (all already have category_id or empty category).")
            return

        updated = 0
        skipped = 0
        for product in products:
            cat_text = product.category.strip().lower()
            slug = CATEGORY_MAPPING.get(cat_text)

            if not slug:
                for key, val in CATEGORY_MAPPING.items():
                    if key in cat_text:
                        slug = val
                        break

            if slug and slug in slug_to_id:
                session.execute(
                    text("UPDATE products SET category_id = :cid WHERE id = :pid"),
                    {"cid": slug_to_id[slug], "pid": product.id},
                )
                updated += 1
            else:
                skipped += 1
                print(f"  SKIP: product {product.id} — unrecognized category '{product.category}'")

        session.commit()
        print(f"Migration complete: {updated} updated, {skipped} skipped out of {len(products)} products.")


if __name__ == "__main__":
    migrate()
