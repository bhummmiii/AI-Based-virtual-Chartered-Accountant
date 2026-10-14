"""
Data Repair Script for Government Updates (K12).
Strictly adheres to:
- Dry-run by default; supply --apply to commit changes.
- NEVER deletes rows (uses hidden=True and hidden_reason).
- Re-derives dates per K3 (never day 01 unless stated; meeting dates mapped; month precision).
- Nulls synthesized / unverified doc numbers per K4.
- Reclassifies administrative / newsletter items per K5.
- Hides non-allowlisted e-Gazette rows per K6.
- Sets backfilled=True on items older than 14 days (before 2026-09-30) or with NULL date per K8.
- Repairs letter-spaced text and clears garbled AI summaries per K7.
- Prints before / after statistics.
"""

import os
import sys
import argparse
from datetime import date, datetime, timezone
from typing import Dict, Any, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import SessionLocal
from app.models.government_update import GovUpdate, GovSource
from app.services.gov_updates.adapters.html_adapter import parse_date_strict
from app.services.gov_updates.normalizer import GovNormalizer, ADMINISTRATIVE_KEYWORDS, AUTHORITY_LAW_SOURCES
from app.services.gov_updates.text_quality import score_text_quality, repair_letter_spaced_text

TODAY = date(2026, 10, 14)
CUTOFF_DATE = date(2026, 9, 30)  # 14 days before 2026-10-14

GST_MEETING_DATE_MAP = {
    "57": date(2026, 10, 8),
    "56": date(2025, 9, 3),
    "55": date(2024, 12, 21),
    "54": date(2024, 9, 9),
    "53": date(2024, 6, 22),
    "52": date(2023, 10, 7),
    "51": date(2023, 8, 2),
    "50": date(2023, 7, 11),
}

EGAZETTE_ALLOWLIST = [
    "ministry of finance",
    "department of revenue",
    "cbic",
    "cbdt",
    "department of economic affairs",
    "department of financial services",
    "ministry of corporate affairs",
    "ministry of law and justice",
    "national financial reporting authority",
    "nfra",
]


def repair_updates(apply: bool = False):
    db = SessionLocal()
    try:
        sources_by_id: Dict[str, GovSource] = {str(s.id): s for s in db.query(GovSource).all()}
        updates: List[GovUpdate] = db.query(GovUpdate).all()

        print(f"\n=======================================================")
        print(f"Gov Updates Data Repair (K12) — Total rows: {len(updates)}")
        print(f"Mode: {'APPLY (Changes will be committed)' if apply else 'DRY RUN (No changes committed)'}")
        print(f"=======================================================\n")

        # Stats counters
        dates_modified = 0
        doc_numbers_nulled = 0
        admin_reclassified = 0
        egazette_hidden = 0
        backfilled_count = 0
        text_repaired = 0
        ai_summary_cleared = 0

        source_counts_before: Dict[str, int] = {}
        source_counts_after_visible: Dict[str, int] = {}

        for u in updates:
            src = sources_by_id.get(str(u.source_id))
            src_code = src.code if src else "unknown"
            source_counts_before[src_code] = source_counts_before.get(src_code, 0) + 1

            changes: List[str] = []

            # -------------------------------------------------------------
            # (a) Re-derive dates per K3
            # -------------------------------------------------------------
            old_date = u.issue_date
            old_prec = u.date_precision
            new_date = old_date
            new_prec = old_prec or "none"
            new_date_src = u.issue_date_source or "none"

            # Check meeting ordinal in title
            import re
            m_match = re.search(r"(\d+)(?:st|nd|rd|th)\s+(?:GST\s+Council\s+Meeting|Meeting\s+of\s+the\s+GST\s+Council)", u.title, re.IGNORECASE)
            if m_match and m_match.group(1) in GST_MEETING_DATE_MAP:
                new_date = GST_MEETING_DATE_MAP[m_match.group(1)]
                new_prec = "day"
                new_date_src = "listing"
            else:
                # Check newsletter month pattern (e.g. December 2025)
                if "newsletter" in u.title.lower() or u.doc_type == "newsletter":
                    nl_d, nl_prec = parse_date_strict(u.title)
                    if nl_d:
                        new_date = nl_d
                        new_prec = nl_prec
                        new_date_src = "listing"
                else:
                    # Check if date is stated in title (e.g. " - (18-08-2026)")
                    t_d, t_prec = parse_date_strict(u.title)
                    if t_d and t_prec == "day":
                        new_date = t_d
                        new_prec = "day"
                        new_date_src = "listing"
                    elif old_date and old_date.day == 1 and new_prec != "month":
                        # If day was artificially set to 01, check if 01 appears in title
                        day_str = "01"
                        if day_str not in u.title and "1st" not in u.title.lower() and "first" not in u.title.lower():
                            # Day was guessed! Nullify date per K3
                            new_date = None
                            new_prec = "none"
                            new_date_src = "none"

            if new_date != old_date or new_prec != old_prec:
                changes.append(f"Date: {old_date} ({old_prec}) -> {new_date} ({new_prec})")
                u.issue_date = new_date
                u.date_precision = new_prec
                u.issue_date_source = new_date_src
                dates_modified += 1

            # -------------------------------------------------------------
            # (b) Null doc numbers that fail K4
            # -------------------------------------------------------------
            old_doc_num = u.doc_number
            if old_doc_num:
                # Check for synthesized formats
                is_synthetic = (
                    old_doc_num.startswith("GSTC-")
                    or old_doc_num.startswith("RBI-ID-")
                    or old_doc_num.startswith("PR-")
                    or old_doc_num.startswith("ICAI-")
                    or "convocation" in old_doc_num.lower()
                    or "exam" in old_doc_num.lower()
                    or "meeting" in old_doc_num.lower()
                )

                # Provenance check: must appear verbatim in title or content_text
                text_to_check = f"{u.title} {u.content_text or ''}".lower()
                in_content = old_doc_num.lower() in text_to_check

                if is_synthetic or not in_content:
                    changes.append(f"Doc Number nulled: '{old_doc_num}' -> None")
                    u.doc_number = None
                    u.doc_number_source = None
                    doc_numbers_nulled += 1

            # -------------------------------------------------------------
            # (c) Reclassify per K5 (administrative/newsletter, legal_status)
            # -------------------------------------------------------------
            is_admin, admin_kw = GovNormalizer.is_administrative(u.title, u.content_text or "")
            if is_admin:
                if "newsletter" in u.title.lower():
                    new_doc_type = "newsletter"
                    new_legal_status = "newsletter"
                elif any(k in u.title.lower() for k in ["exam", "convocation", "training", "cpe", "seminar"]):
                    new_doc_type = "event_or_exam"
                    new_legal_status = "administrative_not_law"
                elif any(k in u.title.lower() for k in ["consultant", "vacancy", "appointment of", "tender"]):
                    new_doc_type = "recruitment_or_tender"
                    new_legal_status = "administrative_not_law"
                else:
                    new_doc_type = "administrative"
                    new_legal_status = "administrative_not_law"

                if u.doc_type != new_doc_type or u.legal_status != new_legal_status or not u.hidden:
                    changes.append(f"Admin reclassify: type={u.doc_type}->{new_doc_type}, status={u.legal_status}->{new_legal_status}, hidden=True")
                    u.doc_type = new_doc_type
                    u.legal_status = new_legal_status
                    u.hidden = True
                    u.hidden_reason = f"administrative_keyword:{admin_kw}"
                    admin_reclassified += 1

            # Press release check
            if "press release" in u.title.lower() and u.legal_status == "operative_instrument":
                changes.append(f"Legal status: operative_instrument -> press_release_not_law")
                u.legal_status = "press_release_not_law"

            # Operative instrument check: GST Council does NOT issue operative instruments directly
            if src_code == "gstcouncil" and u.legal_status == "operative_instrument":
                changes.append(f"GST Council operative -> advisory")
                u.legal_status = "advisory"

            # -------------------------------------------------------------
            # (d) Hide non-allowlisted e-Gazette rows & listing-only links per K6
            # -------------------------------------------------------------
            if src_code == "egazette_recent":
                # Extract ministry from title or field
                min_name = u.ministry or ""
                if not min_name and u.title.startswith("["):
                    end_idx = u.title.find("]")
                    if end_idx != -1:
                        min_name = u.title[1:end_idx]

                min_lower = min_name.lower()
                is_allowlisted = any(allowed in min_lower for allowed in EGAZETTE_ALLOWLIST)
                if not is_allowlisted:
                    if not u.hidden:
                        changes.append(f"e-Gazette non-allowlisted hidden: {min_name}")
                        u.hidden = True
                        u.hidden_reason = f"non_allowlisted_ministry:{min_name or 'unknown'}"
                        egazette_hidden += 1

            if u.link_quality == "listing_only" and not u.hidden:
                changes.append(f"Listing-only link hidden")
                u.hidden = True
                u.hidden_reason = "listing_only_url"

            # -------------------------------------------------------------
            # (e) Set backfilled = True per K8
            # -------------------------------------------------------------
            should_backfill = False
            if u.issue_date is None or u.issue_date < CUTOFF_DATE:
                should_backfill = True

            if should_backfill and not u.backfilled:
                changes.append(f"Backfill: backfilled=True, is_new=False")
                u.backfilled = True
                u.is_new = False
                backfilled_count += 1

            # -------------------------------------------------------------
            # (f) Text quality scoring & letter-spaced repair per K7
            # -------------------------------------------------------------
            if u.content_text:
                score = score_text_quality(u.content_text)
                if score.get("is_letter_spaced"):
                    repaired = repair_letter_spaced_text(u.content_text)
                    rep_score = score_text_quality(repaired)
                    if rep_score.get("is_acceptable"):
                        changes.append(f"Repaired letter-spaced text ({len(u.content_text)} chars)")
                        u.content_text = repaired
                        u.text_status = "ok"
                        text_repaired += 1
                elif not score.get("is_acceptable"):
                    if u.text_status != "unreadable":
                        changes.append(f"Set text_status=unreadable")
                        u.text_status = "unreadable"
                    if u.ai_summary:
                        changes.append(f"Cleared garbled AI summary")
                        u.ai_summary = None
                        ai_summary_cleared += 1

            # Track visible count after repair
            if not u.hidden:
                source_counts_after_visible[src_code] = source_counts_after_visible.get(src_code, 0) + 1

            if changes:
                print(f"[{u.id}] {u.title[:60]}")
                for ch in changes:
                    print(f"   -> {ch}")

        # Summary
        print(f"\n-------------------------------------------------------")
        print(f"Repair Statistics:")
        print(f" - Dates modified/corrected: {dates_modified}")
        print(f" - Synthetic doc numbers nulled: {doc_numbers_nulled}")
        print(f" - Administrative items reclassified & hidden: {admin_reclassified}")
        print(f" - Non-allowlisted e-Gazette rows hidden: {egazette_hidden}")
        print(f" - Rows marked backfilled=True: {backfilled_count}")
        print(f" - Letter-spaced text repaired: {text_repaired}")
        print(f" - Garbled AI summaries cleared: {ai_summary_cleared}")
        print(f"-------------------------------------------------------")

        print("\nVisible Row Counts per Source (Before vs After):")
        for src, b_count in source_counts_before.items():
            a_count = source_counts_after_visible.get(src, 0)
            print(f" - {src:25s}: Total={b_count:2d} | Visible After={a_count:2d}")

        if apply:
            db.commit()
            print("\nSUCCESS: All changes committed to ca_assistant_db.")
        else:
            db.rollback()
            print("\nDRY RUN: No database changes were committed. Run with --apply to commit.")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair gov_updates data (K12).")
    parser.add_argument("--apply", action="store_true", help="Commit changes to database.")
    args = parser.parse_args()
    repair_updates(apply=args.apply)
