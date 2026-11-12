"""
Clean Metadata Structure Script
================================
Scans uploaded documents in the database and cleans any corrupted/nested
metadata_ JSON blobs:
1. Unwraps accidental recursive `fields["fields"]` dictionaries.
2. Hoists structural keys (`table_data`, `line_items`, `line_item_headers`, `hsn_summary`) to top-level metadata.
3. Purges structural keys and container keys from `fields` dictionary.
"""

import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.database.session import SessionLocal
from app.models.uploaded_document import UploadedDocument

def clean_all_metadata():
    db = SessionLocal()
    try:
        docs = db.query(UploadedDocument).filter(UploadedDocument.metadata_.isnot(None)).all()
        updated_count = 0
        structural_keys = (
            "table_data",
            "line_items",
            "line_item_headers",
            "hsn_summary",
            "accuracy_verification",
            "image_quality",
            "cleaned_image_url",
        )

        for doc in docs:
            if not doc.metadata_:
                continue
            try:
                meta = json.loads(doc.metadata_)
                if not isinstance(meta, dict):
                    continue
            except Exception:
                continue

            changed = False
            fields = meta.get("fields")

            # Check if fields is a stringified JSON
            if isinstance(fields, str):
                try:
                    fields = json.loads(fields)
                    meta["fields"] = fields
                    changed = True
                except Exception:
                    pass

            if isinstance(fields, dict):
                # Unwrap recursive "fields" dictionary
                if "fields" in fields:
                    nested = fields.pop("fields")
                    changed = True
                    if isinstance(nested, dict):
                        for nk, nv in nested.items():
                            if nk not in fields:
                                fields[nk] = nv

                # Hoist structural keys to meta root if missing
                for sk in structural_keys:
                    if sk in fields:
                        if sk not in meta:
                            meta[sk] = fields[sk]
                        fields.pop(sk, None)
                        changed = True

                # Purge raw container keys
                for rk in ("fields_raw", "raw"):
                    if rk in fields:
                        fields.pop(rk, None)
                        changed = True

            if changed:
                doc.metadata_ = json.dumps(meta)
                updated_count += 1
                print(f"Cleaned doc #{doc.invoice_number or doc.id} [{doc.document_category}]")

        db.commit()
        print(f"\n[SUCCESS] Cleaned {updated_count} documents in database.")
    finally:
        db.close()

if __name__ == "__main__":
    clean_all_metadata()
