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
    issue_date: Optional[date] = None
    effective_date: Optional[date] = None
    pdf_url: Optional[str] = None
    content_text: Optional[str] = None
    text_status: str = "no_text"  # ok | no_text | too_large
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
