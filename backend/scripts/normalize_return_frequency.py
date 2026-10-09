"""
Script: normalize_return_frequency.py
Audit and normalize GST return filing frequency across all clients.
Complies with Governance Rules:
- Dry-run by default
- --all-clients flag lists all clients and their status
- Applies ONLY case normalisation with --apply (e.g. 'monthly' -> 'Monthly', 'quarterly' -> 'Quarterly')
- NEVER guesses a frequency if null or unrecognised (leaves them as None / flags for manual CA setup)
- Idempotent
"""

import sys
import os
import argparse
from datetime import datetime, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.client import Client
from app.services.gst_filing_service import get_filing_profile


def main():
    parser = argparse.ArgumentParser(description="Audit and normalize return filing frequency across clients.")
    parser.add_argument("--all-clients", action="store_true", default=True, help="Scan all clients in workspace (default True)")
    parser.add_argument("--apply", action="store_true", default=False, help="Apply case normalization to database (default is dry-run)")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        clients = db.query(Client).order_by(Client.created_at.asc()).all()
        print(f"\nScanning {len(clients)} clients for return_frequency normalization...\n")
        print(f"{'Client Code':<12} | {'Company Name':<30} | {'Stored Raw':<15} | {'Normalized':<12} | {'Status'}")
        print("-" * 90)

        changes_to_apply = []
        needs_manual_setup = []

        for c in clients:
            raw = c.return_frequency
            prof = get_filing_profile(c)
            freq = prof["frequency"]  # 'monthly', 'quarterly', or None

            status = "OK"
            target_val = None

            if freq is None:
                status = "REQUIRES MANUAL SETUP (NULL / UNRECOGNIZED)"
                needs_manual_setup.append((c, raw))
            elif freq == "monthly":
                target_val = "Monthly"
                if raw != target_val:
                    status = f"CASE MISMATCH -> will normalize to 'Monthly'"
                    changes_to_apply.append((c, target_val))
            elif freq == "quarterly":
                target_val = "Quarterly"
                if raw != target_val:
                    status = f"CASE MISMATCH -> will normalize to 'Quarterly'"
                    changes_to_apply.append((c, target_val))

            print(f"{c.client_code or 'N/A':<12} | {c.company_name[:28]:<30} | {repr(raw):<15} | {str(target_val):<12} | {status}")

        print("-" * 90)
        print(f"\nSummary:")
        print(f"  Total clients:                  {len(clients)}")
        print(f"  Case normalizations identified: {len(changes_to_apply)}")
        print(f"  Requires manual CA setup:       {len(needs_manual_setup)}")

        if not changes_to_apply:
            print("\n[IDEMPOTENT] No case normalizations needed.")
        else:
            if not args.apply:
                print(f"\n[DRY-RUN] Found {len(changes_to_apply)} clients requiring case normalization.")
                print("Run with --apply to commit case normalization without guessing null values.")
            else:
                for c, target_val in changes_to_apply:
                    old_val = c.return_frequency
                    c.return_frequency = target_val
                    c.updated_at = datetime.now(timezone.utc)
                    print(f"  Applied: {c.client_code} '{old_val}' -> '{target_val}'")
                db.commit()
                print(f"\n[SUCCESS] Successfully applied case normalization to {len(changes_to_apply)} clients.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
