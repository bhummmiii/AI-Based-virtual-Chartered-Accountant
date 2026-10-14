"""
RSS / Atom feed adapter for Government Updates.
Handles RBI notifications, RBI press releases, and standard feeds.
Never guesses dates; if unparseable, returns None.
"""

import re
from datetime import date
from typing import List, Optional
import feedparser
from bs4 import BeautifulSoup

from app.services.gov_updates.adapters.base import RawUpdateItem


def parse_date_from_struct_time(st) -> Optional[date]:
    if not st:
        return None
    try:
        return date(st.tm_year, st.tm_mon, st.tm_mday)
    except Exception:
        return None


def extract_doc_number(title: str, description: str = "") -> Optional[str]:
    combined = f"{title} {description}"

    # Check RBI Notification number format: RBI/2026-27/82
    rbi_match = re.search(r"RBI/\d{4}-\d{2}/\d+", combined, re.IGNORECASE)
    if rbi_match:
        return rbi_match.group(0).upper()

    # Standard doc number patterns: Notification No. 12/2026, Circular No. 214/2026
    std_match = re.search(r"(?:Notification|Circular|Order)\s+(?:No\.?|Number)?\s*([A-Za-z0-9\-/]+)", combined, re.IGNORECASE)
    if std_match:
        return std_match.group(1).strip()

    return None


class RssAdapter:
    @staticmethod
    def parse(xml_content: str, base_source_code: str = "") -> List[RawUpdateItem]:
        feed = feedparser.parse(xml_content)
        items: List[RawUpdateItem] = []

        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue

            # Parse date strictly
            issue_d = parse_date_from_struct_time(getattr(entry, "published_parsed", None))
            if not issue_d:
                issue_d = parse_date_from_struct_time(getattr(entry, "updated_parsed", None))

            # Summary / Description
            raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            soup = BeautifulSoup(raw_summary, "html.parser")
            plain_summary = soup.get_text(separator=" ", strip=True)

            doc_no = extract_doc_number(title, plain_summary)

            items.append(
                RawUpdateItem(
                    title=title,
                    url=link,
                    doc_number=doc_no,
                    doc_number_source="feed" if doc_no else None,
                    issue_date=issue_d,
                    issue_date_source="feed" if issue_d else "none",
                    date_precision="day" if issue_d else "none",
                    content_text=plain_summary if plain_summary else title,
                    text_status="ok" if plain_summary else "no_text",
                    raw_metadata={
                        "feed_id": getattr(entry, "id", link),
                        "tags": [t.term for t in getattr(entry, "tags", []) if hasattr(t, "term")],
                    },
                )
            )

        return items
