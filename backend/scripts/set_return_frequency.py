"""
Script: set_return_frequency.py
Set GST return filing frequency for a specific client.
Complies with Governance Rules:
- Dry-run by default
- --apply requires --client-id (or client code)
- Supported targets: Monthly, Quarterly
- Idempotent: running twice changes nothing the second time
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
    parser = argparse.ArgumentParser(description="Set return filing frequency for a client.")
    parser.add_argument("--client-id", type=str, required=True, help="Client UUID or Client Code (e.g. C-1071)")
    parser.add_argument("--to", type=str, required=True, choices=["Monthly", "Quarterly", "monthly", "quarterly"], help="Target return frequency")
    parser.add_argument("--apply", action="store_true", default=False, help="Commit changes to database (default is dry-run)")

    args = parser.parse_args()
    target_freq = "Quarterly" if args.to.lower().startswith("q") else "Monthly"

    db = SessionLocal()
    try:
        # Search by UUID or client_code
        client = (
            db.query(Client).filter(Client.id == args.client_id).first()
            if len(args.client_id) == 36 and "-" in args.client_id
            else db.query(Client).filter(Client.client_code == args.client_id).first()
        )
        if not client:
            # Fallback search by client_code regardless
            client = db.query(Client).filter(Client.client_code == args.client_id).first()

        if not client:
            print(f"[ERROR] Client '{args.client_id}' not found in database.")
            sys.exit(1)

        current_profile = get_filing_profile(client)
        print(f"\n========================================================")
        print(f"Client: {client.company_name} ({client.client_code}) | ID: {client.id}")
        print(f"Current stored return_frequency: {repr(client.return_frequency)}")
        print(f"Current resolved filing profile: {current_profile}")
        print(f"Target return frequency:         '{target_freq}'")
        print(f"========================================================")

        if client.return_frequency == target_freq:
            print(f"[IDEMPOTENT] Client already has return_frequency='{target_freq}'. No changes needed.")
            return

        if not args.apply:
            print(f"\n[DRY-RUN] Would update client {client.client_code} return_frequency: '{client.return_frequency}' -> '{target_freq}'.")
            print("Run with --apply to commit this change to PostgreSQL.")
            return

        # Apply update
        old_val = client.return_frequency
        client.return_frequency = target_freq
        client.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(client)

        new_profile = get_filing_profile(client)
        print(f"\n[SUCCESS] Updated client {client.client_code} return_frequency: '{old_val}' -> '{client.return_frequency}'.")
        print(f"New resolved filing profile: {new_profile}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
