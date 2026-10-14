"""
Base Adapter and RawUpdateItem structure for government updates adapters.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Dict, Any


@dataclass
class RawUpdateItem:
    title: str
    url: str
    doc_number: Optional[str] = None
    doc_number_source: Optional[str] = None  # listing|feed|detail_page|document_text
    issue_date: Optional[date] = None
    issue_date_source: Optional[str] = "none"  # listing|feed|detail_page|document_text|none
    date_precision: str = "none"  # day|month|year|none
    effective_date: Optional[date] = None
    pdf_url: Optional[str] = None
    content_text: Optional[str] = None
    text_status: str = "no_text"  # ok | no_text | unreadable | too_large
    link_quality: str = "direct_document"  # direct_document | listing_only | homepage
    ministry: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
