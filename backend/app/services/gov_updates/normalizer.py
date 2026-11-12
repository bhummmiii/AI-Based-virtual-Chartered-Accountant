"""
Normalization, Classification, and Deduplication Engine for Government Updates.
Strictly adheres to:
- Deterministic classification of category, doc_type, legal_status
- Press releases ALWAYS tagged 'press_release_not_law'
- Proposals / exposure drafts tagged 'draft_or_proposal'
- Law version tagging (Income-tax Act 2025 vs 1961, CGST Act 2017, Companies Act 2013)
- Supersede / rescind / withdraw detection
- Fixed topics taxonomy
- Content hashing and deduplication
"""

import hashlib
import re
from datetime import date
from typing import List, Tuple, Optional
from app.services.gov_updates.adapters.base import RawUpdateItem

# Fixed topic taxonomy mandated by J1 / J5
FIXED_TOPICS = [
    "rates",
    "returns_filing",
    "due_dates",
    "e_invoicing",
    "e_way_bill",
    "itc",
    "refunds",
    "registration",
    "tds_tcs",
    "accounting_standards",
    "audit",
    "budget",
    "penalties_interest",
    "other",
]

TOPIC_KEYWORDS = {
    "rates": ["rate", "rates", "tariff", "exemption", "concessional", "slab"],
    "returns_filing": ["return", "returns", "gstr-1", "gstr-3b", "gstr-9", "itr", "filing", "form"],
    "due_dates": ["due date", "extension", "last date", "extended till", "timeline"],
    "e_invoicing": ["e-invoicing", "e-invoice", "einvoice", "irn", "qr code"],
    "e_way_bill": ["e-way bill", "eway bill", "ewb", "part b"],
    "itc": ["input tax credit", "itc", "gstr-2b", "credit reversal", "rule 36(4)", "section 16"],
    "refunds": ["refund", "refunds", "accumulated itc", "inverted duty"],
    "registration": ["registration", "aadhaar", "biometric", "cancellation", "revocation"],
    "tds_tcs": ["tds", "tcs", "tax deducted at source", "194q", "206c", "virtual digital assets"],
    "accounting_standards": ["accounting standard", "ind as", "as-", "standard setting", "exposure draft", "nfra"],
    "audit": ["audit", "tax audit", "statutory audit", "special audit", "auditor"],
    "budget": ["budget", "finance act", "finance bill", "memorandum", "direct tax proposals"],
    "penalties_interest": ["penalty", "penalties", "interest", "late fee", "waiver", "amnesty", "prosecution"],
}


ADMINISTRATIVE_KEYWORDS = [
    "vacancy",
    "recruitment",
    "appointment of",
    "deputation",
    "empanelment",
    "consultant",
    "tender",
    "rfp",
    "newsletter",
    "award",
    "nomination",
    "exam",
    "examination",
    "webinar",
    "training",
    "cpe",
    "seminar",
    "membership",
    "convocation",
]

AUTHORITY_LAW_SOURCES = {
    "cbic_gst",
    "cbic_taxinfo",
    "incometax_feed",
    "mca",
    "rbi_notifications",
    "sebi_circulars",
    "egazette_recent",
    "dor",
    "gstat",
    "nfra_orders",
}


def compute_content_hash(title: str, content_text: Optional[str], doc_number: Optional[str], issue_date: Optional[date]) -> str:
    """Computes SHA-256 hash for content change detection."""
    payload = f"{title.strip()}\n{(content_text or '').strip()}\n{doc_number or ''}\n{issue_date or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class GovNormalizer:
    @classmethod
    def is_administrative(cls, title: str, text: str) -> Tuple[bool, Optional[str]]:
        """
        Detects administrative, recruitment, exam or newsletter items (K5).
        Returns (is_admin, matched_keyword).
        """
        snippet = f"{title} {text[:500]}".lower()
        for kw in ADMINISTRATIVE_KEYWORDS:
            if kw in snippet:
                return True, kw
        return False, None

    @classmethod
    def classify_category(cls, source_code: str, title: str, text: str) -> str:
        combined = f"{title} {text}".lower()

        # Content keyword rules (evaluated first so specialized circulars match accurately)
        if any(k in combined for k in ["tds", "tcs", "tax deducted", "section 194"]):
            return "TDS"
        if any(k in combined for k in ["gst", "cgst", "igst", "sgst", "gstin", "gstr"]):
            return "GST"
        if any(k in combined for k in ["income-tax", "income tax", "cbdt", "tax audit", "section 44ab", "direct tax", "tax year", "itr"]):
            return "INCOME_TAX"
        if any(k in combined for k in ["budget", "finance act", "finance bill", "standard deduction", "union budget"]):
            return "BUDGET"
        if any(k in combined for k in ["accounting standard", "ind as", "auditing", "nfra", "icai"]):
            return "ACCOUNTING"
        if any(k in combined for k in ["companies act", "mca", "roc", "corporate affairs", "sebi"]):
            return "COMPANIES"
        if any(k in combined for k in ["repo rate", "fema", "foreign exchange", "government securities", "omo sale"]):
            return "BANKING"

        # Source code fallbacks
        if source_code == "gstcouncil":
            return "GST"
        if source_code == "incometax_feed":
            return "INCOME_TAX"
        if source_code == "indiabudget":
            return "BUDGET"
        if source_code == "dor":
            return "INCOME_TAX"
        if source_code in ("rbi_notifications", "rbi_pressreleases"):
            return "BANKING"
        if source_code in ("icai_announcements", "nfra_orders", "icai_idtc"):
            return "ACCOUNTING"
        if source_code in ("sebi_circulars", "mca"):
            return "COMPANIES"

        return "OTHER"

    @classmethod
    def classify_doc_type(cls, title: str, url: str, text: str = "") -> str:
        combined = f"{title} {url} {text[:500]}".lower()

        # Administrative classifications (K5)
        if "newsletter" in combined:
            return "newsletter"
        if any(k in combined for k in ["exam", "examination", "webinar", "training", "cpe", "seminar", "convocation"]):
            return "event_or_exam"
        if any(k in combined for k in ["vacancy", "recruitment", "deputation", "empanelment", "consultant", "tender", "rfp", "appointment of"]):
            return "recruitment_or_tender"

        if any(k in combined for k in ["press release", "press_release", "pr-", "prid="]):
            return "press_release"
        if "faq" in combined or "frequently asked" in combined:
            return "faq"
        if "circular" in combined:
            return "circular"
        if "notification" in combined:
            return "notification"
        if "gazette" in combined:
            return "gazette"
        if "order" in combined:
            return "order"
        if "instruction" in combined:
            return "instruction"
        if "advisory" in combined:
            return "advisory"
        if any(k in combined for k in ["standard", "ind as", "exposure draft"]):
            return "standard"
        if "rules" in combined:
            return "rules"
        if "act" in combined or "bill" in combined:
            return "act"

        return "other"

    @classmethod
    def classify_legal_status(cls, doc_type: str, title: str, text: str, source_code: str = "", category: str = "") -> str:
        """
        Determines legal enforceability strictly per K5.
        operative_instrument ONLY when:
        - doc_type in (notification, circular, order, instruction, rules, act)
        - NOT administrative
        - category in (GST, INCOME_TAX, TDS, COMPANIES, ACCOUNTING, BANKING)
        - source is an authority that issues law
        """
        combined = f"{title} {text[:500]}".lower()

        # Administrative check (K5)
        is_admin, _ = cls.is_administrative(title, text)
        if is_admin:
            if doc_type == "newsletter":
                return "newsletter"
            return "administrative_not_law"

        if doc_type == "press_release" or "press release" in combined or "press note" in combined:
            return "press_release_not_law"

        if any(k in combined for k in ["exposure draft", "draft", "proposal", "consultation paper"]):
            return "draft_or_proposal"

        if doc_type == "faq" or "faq" in combined or "frequently asked" in combined:
            return "explanatory"

        if doc_type == "advisory" or "advisory" in combined:
            return "advisory"

        # Operative Instrument strictly restricted per K5
        LAW_DOC_TYPES = {"circular", "notification", "order", "instruction", "rules", "act"}
        LAW_CATEGORIES = {"GST", "INCOME_TAX", "TDS", "COMPANIES", "ACCOUNTING", "BANKING"}

        if (
            doc_type in LAW_DOC_TYPES
            and (category in LAW_CATEGORIES or not category)
            and (source_code in AUTHORITY_LAW_SOURCES or not source_code)
        ):
            return "operative_instrument"

        if doc_type in LAW_DOC_TYPES:
            # Non-law authority (e.g. GST Council, ICAI non-law)
            return "advisory"

        return "unknown"

    @classmethod
    def detect_law_version(cls, title: str, text: str) -> str:
        """
        Tags statutory law version.
        Distinguishes Income-tax Act, 2025 vs Income-tax Act, 1961.
        """
        combined = f"{title} {text}".lower()

        # Income-tax Act, 2025 (in force from 1 April 2026)
        if (
            "income-tax act, 2025" in combined
            or "income-tax act 2025" in combined
            or "income tax act, 2025" in combined
            or "income-tax rules, 2026" in combined
            or "tax year 20" in combined
        ):
            return "Income-tax Act, 2025"

        # Income-tax Act, 1961
        if (
            "income-tax act, 1961" in combined
            or "income-tax act 1961" in combined
            or "income tax act, 1961" in combined
            or "assessment year" in combined
            or "previous year" in combined
        ):
            return "Income-tax Act, 1961"

        # GST Acts
        if any(k in combined for k in ["cgst act", "central goods and services tax act", "igst act", "utgst act"]):
            return "CGST Act 2017"

        # Companies Act
        if "companies act, 2013" in combined or "companies act 2013" in combined:
            return "Companies Act 2013"

        # RBI Act
        if "reserve bank of india act" in combined or "rbi act, 1934" in combined or "rbi act 1934" in combined:
            return "RBI Act 1934"

        return "unknown"

    @classmethod
    def detect_supersedes(cls, title: str, text: str) -> Tuple[str, float, List[str]]:
        """
        Detects supersede/rescind/withdraw phrases and referenced doc numbers.
        Returns (status, status_confidence, supersedes_refs).
        """
        combined = f"{title} {text}".lower()
        supersedes_refs: List[str] = []

        patterns = [
            r"(?:supersedes|in supersession of|superseding)\s+(?:circular|notification|order)?\s*(?:no\.?)?\s*([A-Za-z0-9\-/]+)",
            r"(?:rescinds|in rescission of|rescinding)\s+(?:notification|circular)?\s*(?:no\.?)?\s*([A-Za-z0-9\-/]+)",
            r"(?:withdrawn|withdrawing)\s+(?:vide|circular|notification)?\s*(?:no\.?)?\s*([A-Za-z0-9\-/]+)",
        ]

        for pat in patterns:
            matches = re.finditer(pat, combined, re.IGNORECASE)
            for m in matches:
                ref = m.group(1).strip()
                if len(ref) > 2 and ref not in supersedes_refs:
                    supersedes_refs.append(ref)

        if "withdrawn" in combined:
            return "withdrawn", 0.95, supersedes_refs
        if "amended" in combined or "amendment" in combined:
            return "amended", 0.85, supersedes_refs
        if supersedes_refs:
            return "active", 0.90, supersedes_refs

        return "active", 1.0, []

    @classmethod
    def extract_topics(cls, title: str, text: str) -> List[str]:
        """Extracts matching topics strictly from the fixed taxonomy."""
        combined = f"{title} {text}".lower()
        matched_topics = set()

        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(k in combined for k in keywords):
                matched_topics.add(topic)

        if not matched_topics:
            matched_topics.add("other")

        # Guarantee all returned topics are members of FIXED_TOPICS
        return [t for t in FIXED_TOPICS if t in matched_topics]

    @classmethod
    def normalize_item(cls, raw: RawUpdateItem, source_code: str) -> dict:
        """
        Takes RawUpdateItem and produces full normalized attributes ready for persistence.
        """
        content_txt = raw.content_text or ""
        cat = cls.classify_category(source_code, raw.title, content_txt)
        doc_tp = cls.classify_doc_type(raw.title, raw.url, content_txt)
        leg_st = cls.classify_legal_status(doc_tp, raw.title, content_txt, source_code=source_code, category=cat)
        law_ver = cls.detect_law_version(raw.title, content_txt)
        status, confidence, supersedes_refs = cls.detect_supersedes(raw.title, content_txt)
        topics = cls.extract_topics(raw.title, content_txt)

        # K4: doc_number provenance check - MUST occur in title or content_text
        doc_num = raw.doc_number.strip() if raw.doc_number else None
        doc_num_source = raw.doc_number_source
        if doc_num:
            if not (doc_num.lower() in raw.title.lower() or (content_txt and doc_num.lower() in content_txt.lower())):
                doc_num = None
                doc_num_source = None

        # K5: Administrative items hidden by default
        is_admin, admin_kw = cls.is_administrative(raw.title, content_txt)
        hidden = False
        hidden_reason = None
        if is_admin:
            hidden = True
            hidden_reason = f"administrative_keyword:{admin_kw}"
        elif raw.link_quality == "listing_only":
            hidden = True
            hidden_reason = "listing_only_url"

        c_hash = compute_content_hash(raw.title, content_txt, doc_num, raw.issue_date)

        return {
            "title": raw.title.strip(),
            "doc_type": doc_tp,
            "legal_status": leg_st,
            "doc_number": doc_num,
            "doc_number_source": doc_num_source,
            "issue_date": raw.issue_date,
            "issue_date_source": raw.issue_date_source or ("listing" if raw.issue_date else "none"),
            "date_precision": raw.date_precision or ("day" if raw.issue_date else "none"),
            "effective_date": raw.effective_date,
            "category": cat,
            "topics": topics,
            "law_version": law_ver,
            "url": raw.url.strip(),
            "link_quality": raw.link_quality,
            "ministry": raw.ministry,
            "pdf_url": raw.pdf_url.strip() if raw.pdf_url else None,
            "content_text": content_txt,
            "text_status": raw.text_status,
            "content_hash": c_hash,
            "status": status,
            "status_confidence": confidence,
            "supersedes_refs": supersedes_refs,
            "hidden": hidden,
            "hidden_reason": hidden_reason,
        }
