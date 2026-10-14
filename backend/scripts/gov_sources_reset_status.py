"""
Reset GovSource Statuses based on Probe Results (K1).
Dry-run by default; supply --apply to commit changes.
Applies probe decisions per K1:
- ok (enabled): rbi_notifications, rbi_pressreleases, gstcouncil, icai_announcements, nfra_orders, sebi_circulars, egazette_recent
- blocked_requires_verification (disabled): gstn_news, incometax_feed, pib_rss, mca, indiabudget
- unreachable (disabled): cbic_taxinfo, cbic_gst, finmin, dor, mahagst
"""

import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import SessionLocal
from app.models.government_update import GovSource

TARGET_STATUS_MAP = {
    # Enabled OK sources
    "rbi_notifications": {
        "status": "ok",
        "enabled": True,
        "failure_stage": None,
        "last_error": None,
        "consecutive_failures": 0,
    },
    "rbi_pressreleases": {
        "status": "ok",
        "enabled": True,
        "failure_stage": None,
        "last_error": None,
        "consecutive_failures": 0,
    },
    "gstcouncil": {
        "status": "ok",
        "enabled": True,
        "failure_stage": None,
        "last_error": None,
        "consecutive_failures": 0,
    },
    "icai_announcements": {
        "status": "ok",
        "enabled": True,
        "failure_stage": None,
        "last_error": None,
        "consecutive_failures": 0,
    },
    "egazette_recent": {
        "status": "ok",
        "enabled": True,
        "failure_stage": None,
        "last_error": None,
        "consecutive_failures": 0,
    },
    "nfra_orders": {
        "status": "ok",
        "enabled": True,
        "failure_stage": None,
        "last_error": None,
        "consecutive_failures": 0,
    },
    "sebi_circulars": {
        "status": "ok",
        "enabled": True,
        "failure_stage": None,
        "last_error": None,
        "consecutive_failures": 0,
    },

    # Blocked (WAF 403 challenge) sources
    "gstn_news": {
        "status": "blocked_requires_verification",
        "enabled": False,
        "failure_stage": "http_challenge",
        "last_error": "HTTP 403 WAF bot challenge detected on /newsandupdates",
        "consecutive_failures": 1,
    },
    "incometax_feed": {
        "status": "blocked_requires_verification",
        "enabled": False,
        "failure_stage": "http_challenge",
        "last_error": "HTTP 403 WAF challenge on /tax-feeds and direct RSS feeds",
        "consecutive_failures": 1,
    },
    "pib_rss": {
        "status": "blocked_requires_verification",
        "enabled": False,
        "failure_stage": "http_challenge",
        "last_error": "HTTP 403 WAF challenge on /RssMain.aspx",
        "consecutive_failures": 1,
    },
    "mca": {
        "status": "blocked_requires_verification",
        "enabled": False,
        "failure_stage": "http_challenge",
        "last_error": "HTTP 403 WAF challenge detected during probe",
        "consecutive_failures": 1,
    },
    "indiabudget": {
        "status": "blocked_requires_verification",
        "enabled": False,
        "failure_stage": "http_challenge",
        "last_error": "HTTP 403 WAF challenge detected on indiabudget.gov.in",
        "consecutive_failures": 1,
    },

    # Unreachable / Degraded sources
    "cbic_taxinfo": {
        "status": "unreachable",
        "enabled": False,
        "failure_stage": "tcp",
        "last_error": "Connection timed out to 163.227.109.58:443 during probe",
        "consecutive_failures": 3,
    },
    "cbic_gst": {
        "status": "unreachable",
        "enabled": False,
        "failure_stage": "tls",
        "last_error": "TLS handshake failure on cbic-gst.gov.in:443",
        "consecutive_failures": 3,
    },
    "finmin": {
        "status": "unreachable",
        "enabled": False,
        "failure_stage": "tcp",
        "last_error": "Connection timed out to 164.100.154.21:443 (10s)",
        "consecutive_failures": 3,
    },
    "dor": {
        "status": "unreachable",
        "enabled": False,
        "failure_stage": "tcp",
        "last_error": "Connection timed out to dor.gov.in during probe",
        "consecutive_failures": 3,
    },
    "mahagst": {
        "status": "unreachable",
        "enabled": False,
        "failure_stage": "tcp",
        "last_error": "Host connection timed out / subpaths redirected to login",
        "consecutive_failures": 3,
    },
}


def reset_statuses(apply: bool = False):
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    cooldown = now + timedelta(hours=24)

    print("\n=======================================================")
    print(f"GOV SOURCES STATUS RESET (K1) — {'[APPLY MODE]' if apply else '[DRY RUN]'}")
    print("=======================================================\n")

    changes = []
    for s in db.query(GovSource).order_by(GovSource.code).all():
        cfg = TARGET_STATUS_MAP.get(s.code)
        if not cfg:
            continue

        diffs = []
        if s.status != cfg["status"]:
            diffs.append(f"status: '{s.status}' -> '{cfg['status']}'")
        if s.enabled != cfg["enabled"]:
            diffs.append(f"enabled: {s.enabled} -> {cfg['enabled']}")
        if s.failure_stage != cfg["failure_stage"]:
            diffs.append(f"failure_stage: '{s.failure_stage}' -> '{cfg['failure_stage']}'")
        if s.last_error != cfg["last_error"]:
            diffs.append(f"last_error: updated")

        if diffs:
            changes.append((s, diffs, cfg))

    if not changes:
        print("All 17 sources already match the target probe statuses. No changes needed.")
        db.close()
        return

    for s, diffs, cfg in changes:
        print(f"Source: {s.code:22}")
        for d in diffs:
            print(f"  - {d}")

        if apply:
            s.status = cfg["status"]
            s.enabled = cfg["enabled"]
            s.failure_stage = cfg["failure_stage"]
            s.last_error = cfg["last_error"]
            s.consecutive_failures = cfg["consecutive_failures"]
            s.last_probe_at = now
            if cfg["status"] in ("blocked_requires_verification", "unreachable"):
                s.next_retry_at = cooldown
            else:
                s.next_retry_at = None
                s.last_error = None  # Cleared when ok

    if apply:
        db.commit()
        print(f"\nSuccessfully applied updates to {len(changes)} sources in live database!")
    else:
        print(f"\nDry run complete. Found {len(changes)} sources needing updates. Re-run with --apply to commit.")

    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset gov source statuses per K1.")
    parser.add_argument("--apply", action="store_true", help="Apply updates to database")
    args = parser.parse_args()
    reset_statuses(apply=args.apply)
