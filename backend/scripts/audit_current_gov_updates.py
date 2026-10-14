"""
Phase A Data Audit Script (A3).
Audits current gov_updates database rows without modifying data:
- Counts by source / doc_type / legal_status / date_precision
- Rows with day = 01 derived/guessed
- Rows with synthetic doc numbers not found in text/listing (#GSTC-...)
- Rows tagged operative_instrument matching K5 administrative keywords
- e-Gazette rows by ministry
- Rows whose URL equals source base/listing URL
- Rows with garbled / letter-spaced text
- Rows marked New older than 14 days
- Rows from disabled/blocked sources
"""

import os
import sys
import re
from datetime import datetime, timezone, timedelta
from collections import Counter
from sqlalchemy import func

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import SessionLocal
from app.models.government_update import GovSource, GovUpdate


ADMIN_KEYWORDS = [
    "vacancy", "recruitment", "appointment of", "deputation", "empanelment",
    "consultant", "tender", "rfp", "newsletter", "award", "nomination",
    "exam", "examination", "webinar", "training", "cpe", "seminar",
    "membership", "convocation"
]


def score_text_quality(text: str) -> dict:
    if not text or len(text.strip()) < 50:
        return {"quality": "empty_or_short", "is_garbled": True, "reason": "too short"}

    # Printable ratio
    printable_count = sum(1 for c in text if c.isprintable())
    printable_ratio = printable_count / len(text)
    if printable_ratio < 0.85:
        return {"quality": "unprintable", "is_garbled": True, "reason": "unprintable chars"}

    # Letter-spaced check: e.g. "M E S S A G E   T h e   F i f t h"
    tokens = text.split()
    if len(tokens) >= 10:
        single_char_tokens = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
        single_char_ratio = single_char_tokens / len(tokens)
        if single_char_ratio >= 0.60:
            return {"quality": "letter_spaced", "is_garbled": True, "reason": f"letter_spaced ratio {single_char_ratio:.2f}"}

    return {"quality": "ok", "is_garbled": False, "reason": "clean"}


def run_audit():
    db = SessionLocal()
    total_updates = db.query(GovUpdate).count()
    print(f"\n=======================================================")
    print(f"GOVERNMENT UPDATES DATA AUDIT (A3) — Total Rows: {total_updates}")
    print(f"=======================================================\n")

    # 1. Counts by source
    print("--- 1. Counts by Source ---")
    sources = db.query(GovSource).order_by(GovSource.code).all()
    for s in sources:
        cnt = db.query(GovUpdate).filter(GovUpdate.source_id == s.id).count()
        print(f"  {s.code:22} ({s.status:28}, enabled={s.enabled}): {cnt} rows")

    # 2. Counts by doc_type
    print("\n--- 2. Counts by doc_type ---")
    dt_counts = Counter(row[0] for row in db.query(GovUpdate.doc_type).all())
    for dt, cnt in dt_counts.most_common():
        print(f"  {dt:25}: {cnt} rows")

    # 3. Counts by legal_status
    print("\n--- 3. Counts by legal_status ---")
    ls_counts = Counter(row[0] for row in db.query(GovUpdate.legal_status).all())
    for ls, cnt in ls_counts.most_common():
        print(f"  {ls:25}: {cnt} rows")

    # 4. Dates with day = 01 (potential URL month extraction)
    all_updates = db.query(GovUpdate).all()
    day_01_rows = [u for u in all_updates if u.issue_date and u.issue_date.day == 1]
    print(f"\n--- 4. Rows with Day = 01 Dates: {len(day_01_rows)} rows ---")
    for u in day_01_rows[:10]:
        print(f"  [{u.issue_date}] {u.title[:70]} (URL: {u.url[:60]})")

    # 5. Invented / synthesized doc numbers (e.g. #GSTC-...)
    synth_doc_rows = []
    for u in all_updates:
        if u.doc_number:
            num = u.doc_number.strip().lstrip("#")
            txt = (u.title or "") + " " + (u.content_text or "")
            if num.upper().startswith("GSTC-") or (num.lower() not in txt.lower()):
                synth_doc_rows.append((u, num))
    print(f"\n--- 5. Rows with Synthesized/Untraced Document Numbers: {len(synth_doc_rows)} rows ---")
    for u, num in synth_doc_rows[:10]:
        print(f"  Num: '{num}' | Title: {u.title[:70]}")

    # 6. Operative instruments matching administrative keywords
    admin_mislabeled = []
    for u in all_updates:
        if u.legal_status == "operative_instrument":
            search_corpus = (u.title or "")[:500] + " " + (u.content_text or "")[:500]
            matched_kw = [kw for kw in ADMIN_KEYWORDS if re.search(r'\b' + kw + r'\b', search_corpus, re.I)]
            if matched_kw:
                admin_mislabeled.append((u, matched_kw))
    print(f"\n--- 6. Operative Instruments matching Administrative Keywords: {len(admin_mislabeled)} rows ---")
    for u, kws in admin_mislabeled[:10]:
        print(f"  KWs: {kws} | Title: {u.title[:70]}")

    # 7. e-Gazette rows by ministry
    egaz_src = db.query(GovSource).filter(GovSource.code == "egazette_recent").first()
    if egaz_src:
        egaz_rows = db.query(GovUpdate).filter(GovUpdate.source_id == egaz_src.id).all()
        ministries = []
        for r in egaz_rows:
            m = re.search(r'\[(.*?)\]', r.title or "")
            ministries.append(m.group(1) if m else "Unknown / Unstated")
        print(f"\n--- 7. e-Gazette Rows by Ministry ({len(egaz_rows)} total rows) ---")
        for m_name, m_cnt in Counter(ministries).most_common():
            print(f"  {m_name:40}: {m_cnt} rows")

    # 8. Rows whose URL equals source base/listing URL
    listing_url_rows = []
    for u in all_updates:
        s = u.source
        if s and (u.url == s.base_url or u.url.rstrip('/') == s.base_url.rstrip('/') or "HomeAction.do" in u.url):
            listing_url_rows.append(u)
    print(f"\n--- 8. Rows whose URL equals Source Listing/Base URL: {len(listing_url_rows)} rows ---")
    for u in listing_url_rows[:10]:
        print(f"  Source: {u.source.code:18} | URL: {u.url}")

    # 9. Garbled / letter-spaced text
    garbled_rows = []
    for u in all_updates:
        q_res = score_text_quality(u.content_text or "")
        if q_res["is_garbled"]:
            garbled_rows.append((u, q_res))
    print(f"\n--- 9. Rows with Garbled / Letter-Spaced Text: {len(garbled_rows)} rows ---")
    for u, q in garbled_rows[:10]:
        print(f"  Reason: {q['reason']:30} | Title: {u.title[:60]}")

    # 10. Rows marked New that are older than 14 days
    now = datetime.now(timezone.utc).date()
    cutoff_14d = now - timedelta(days=14)
    old_new_rows = []
    for u in all_updates:
        # Check if issue_date < cutoff_14d
        if u.issue_date and u.issue_date < cutoff_14d and not u.backfilled:
            old_new_rows.append(u)
    print(f"\n--- 10. Rows with issue_date > 14 days ago (older than {cutoff_14d}) not marked backfilled: {len(old_new_rows)} rows ---")
    for u in old_new_rows[:10]:
        print(f"  [{u.issue_date}] Title: {u.title[:70]}")

    # 11. Rows from disabled or blocked sources
    disabled_source_rows = []
    for u in all_updates:
        if u.source and (not u.source.enabled or u.source.status in ("disabled", "blocked_requires_verification", "unreachable")):
            disabled_source_rows.append(u)
    print(f"\n--- 11. Rows from currently Disabled/Blocked/Unreachable sources: {len(disabled_source_rows)} rows ---")

    db.close()


if __name__ == "__main__":
    run_audit()
