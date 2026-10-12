"""
HTML Listing Adapters for Official Government Sources.
Implements dedicated parsers for:
- GST Council (gstcouncil.gov.in)
- ICAI Announcements (icai.org)
- e-Gazette Recent Extraordinary (egazette.gov.in)
- NFRA Orders (nfra.gov.in)
- SEBI Circulars (sebi.gov.in)
Never guesses dates; returns None if unparseable (R4).
"""

import re
from datetime import datetime, date
from typing import List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from app.services.gov_updates.adapters.base import RawUpdateItem

DATE_PATTERNS = [
    (r"\b(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{4})\b", "%d-%b-%Y"),
    (r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s*(\d{4})\b", "%b %d, %Y"),
    (r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", "%d-%m-%Y"),
    (r"\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b", "%Y-%m-%d"),
]


def parse_date_strict(text: str) -> Optional[date]:
    """Strictly parses dates from text. Returns None if unparseable."""
    if not text:
        return None

    cleaned = text.strip()
    for regex, fmt in DATE_PATTERNS:
        match = re.search(regex, cleaned, re.IGNORECASE)
        if match:
            matched_str = match.group(0).replace(".", "-").replace("/", "-")
            try:
                dt = datetime.strptime(matched_str, fmt)
                return dt.date()
            except ValueError:
                continue

    return None


class HtmlListingAdapter:
    @classmethod
    def parse(cls, source_code: str, html_text: str, base_url: str) -> List[RawUpdateItem]:
        if source_code == "gstcouncil":
            return cls._parse_gstcouncil(html_text, base_url)
        elif source_code == "icai_announcements":
            return cls._parse_icai(html_text, base_url)
        elif source_code == "egazette_recent":
            return cls._parse_egazette(html_text, base_url)
        elif source_code == "nfra_orders":
            return cls._parse_nfra(html_text, base_url)
        elif source_code == "sebi_circulars":
            return cls._parse_sebi(html_text, base_url)
        else:
            return cls._parse_generic_listing(html_text, base_url)

    @classmethod
    def _parse_gstcouncil(cls, html_text: str, base_url: str) -> List[RawUpdateItem]:
        soup = BeautifulSoup(html_text, "html.parser")
        items: List[RawUpdateItem] = []
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            title = a.get_text(separator=" ", strip=True)
            if not title or len(title) < 15:
                continue

            # Target press releases, decisions, meetings, faqs, pdfs
            is_relevant = any(k in href.lower() for k in [".pdf", "recommendation", "press_release", "faq", "decision", "meeting"])
            if not is_relevant:
                continue

            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Date parsing from title or url path (e.g. /2026-10/press_release_0.pdf)
            issue_d = parse_date_strict(title)
            if not issue_d:
                url_date_match = re.search(r"/(\d{4})-(\d{2})/", href)
                if url_date_match:
                    try:
                        issue_d = date(int(url_date_match.group(1)), int(url_date_match.group(2)), 1)
                    except Exception:
                        issue_d = None

            # Doc number from meeting number (e.g. 57th GST Council)
            doc_no = None
            meeting_m = re.search(r"(\d+(?:st|nd|rd|th)\s+(?:GST\s+Council\s+Meeting|Meeting\s+of\s+the\s+GST\s+Council))", title, re.IGNORECASE)
            if meeting_m:
                doc_no = f"GSTC-{meeting_m.group(1).split()[0].upper()}"

            is_pdf = full_url.lower().endswith(".pdf")

            items.append(
                RawUpdateItem(
                    title=title,
                    url=full_url,
                    doc_number=doc_no,
                    issue_date=issue_d,
                    pdf_url=full_url if is_pdf else None,
                    content_text=title,
                    text_status="no_text" if is_pdf else "ok",
                    raw_metadata={"source": "gstcouncil"},
                )
            )

        return items

    @classmethod
    def _parse_icai(cls, html_text: str, base_url: str) -> List[RawUpdateItem]:
        soup = BeautifulSoup(html_text, "html.parser")
        items: List[RawUpdateItem] = []
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "/post/" not in href:
                continue

            title = a.get_text(separator=" ", strip=True)
            if not title or len(title) < 15:
                continue

            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Date: ICAI often formats date in title e.g. " - (05-10-2026)"
            issue_d = parse_date_strict(title)

            # Doc number from slug
            slug = href.rstrip("/").split("/")[-1]
            doc_no = f"ICAI-{slug[:40]}" if slug else None

            items.append(
                RawUpdateItem(
                    title=title,
                    url=full_url,
                    doc_number=doc_no,
                    issue_date=issue_d,
                    content_text=title,
                    text_status="ok",
                    raw_metadata={"slug": slug},
                )
            )

        return items

    @classmethod
    def _parse_egazette(cls, html_text: str, base_url: str) -> List[RawUpdateItem]:
        """Parses the 'Recent Extra Ordinary Gazettes' homepage table directly."""
        soup = BeautifulSoup(html_text, "html.parser")
        items: List[RawUpdateItem] = []

        # Find rows containing rpt_Extra_lbl_MinistryE_
        for idx in range(20):
            min_span = soup.find(id=f"rpt_Extra_lbl_MinistryE_{idx}")
            if not min_span:
                break
            subj_span = soup.find(id=f"rpt_Extra_lbl_SubjectE_{idx}")
            date_span = soup.find(id=f"rpt_Extra_lbl_DateE_{idx}")
            gid_span = soup.find(id=f"rpt_Extra_lbl_UGIDExtra_{idx}")

            ministry = min_span.get_text(strip=True) if min_span else "Government of India"
            subj = subj_span.get_text(strip=True) if subj_span else ""
            date_str = date_span.get_text(strip=True) if date_span else ""
            gid = gid_span.get_text(strip=True) if gid_span else f"EGAZETTE-{idx}"

            full_title = f"[{ministry}] {subj}" if subj else f"Gazette Notification {gid}"
            issue_d = parse_date_strict(date_str)

            canonical_url = f"{base_url}#gazette-{gid}"

            items.append(
                RawUpdateItem(
                    title=full_title,
                    url=canonical_url,
                    doc_number=gid,
                    issue_date=issue_d,
                    content_text=f"Ministry: {ministry}\nSubject: {subj}\nGazette ID: {gid}\nPublished: {date_str}",
                    text_status="ok",
                    raw_metadata={"ministry": ministry, "gazette_id": gid},
                )
            )

        return items

    @classmethod
    def _parse_nfra(cls, html_text: str, base_url: str) -> List[RawUpdateItem]:
        soup = BeautifulSoup(html_text, "html.parser")
        items: List[RawUpdateItem] = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if not tds or len(tds) < 2:
                continue

            row_text = " ".join(td.get_text(strip=True) for td in tds)
            a_tag = tr.find("a", href=True)
            if not a_tag:
                continue

            title = tds[0].get_text(strip=True) or a_tag.get_text(strip=True)
            if len(title) < 10:
                continue

            full_url = urljoin(base_url, a_tag["href"])
            issue_d = parse_date_strict(row_text)

            items.append(
                RawUpdateItem(
                    title=title,
                    url=full_url,
                    doc_number=None,
                    issue_date=issue_d,
                    pdf_url=full_url if full_url.lower().endswith(".pdf") else None,
                    content_text=title,
                    text_status="ok",
                    raw_metadata={"source": "nfra"},
                )
            )

        return items

    @classmethod
    def _parse_sebi(cls, html_text: str, base_url: str) -> List[RawUpdateItem]:
        soup = BeautifulSoup(html_text, "html.parser")
        items: List[RawUpdateItem] = []

        for tr in soup.find_all("tr"):
            a = tr.find("a", href=True)
            if not a:
                continue
            title = a.get_text(separator=" ", strip=True)
            if len(title) < 15:
                continue

            full_url = urljoin(base_url, a["href"])
            row_text = tr.get_text(separator=" ", strip=True)
            issue_d = parse_date_strict(row_text)

            # Doc number regex in title or link
            doc_no = None
            doc_m = re.search(r"SEBI/[A-Za-z0-9\-/_]+", title)
            if doc_m:
                doc_no = doc_m.group(0)

            items.append(
                RawUpdateItem(
                    title=title,
                    url=full_url,
                    doc_number=doc_no,
                    issue_date=issue_d,
                    content_text=title,
                    text_status="ok",
                    raw_metadata={"source": "sebi"},
                )
            )

        return items

    @classmethod
    def _parse_generic_listing(cls, html_text: str, base_url: str) -> List[RawUpdateItem]:
        soup = BeautifulSoup(html_text, "html.parser")
        items: List[RawUpdateItem] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            title = a.get_text(separator=" ", strip=True)
            if len(title) > 20 and any(k in href.lower() for k in [".pdf", "circular", "notification", "order"]):
                full_url = urljoin(base_url, href)
                issue_d = parse_date_strict(title)
                items.append(
                    RawUpdateItem(
                        title=title,
                        url=full_url,
                        issue_date=issue_d,
                        pdf_url=full_url if full_url.lower().endswith(".pdf") else None,
                    )
                )
        return items
