"""
Shared structures + formatting helpers for the AI assistant tools.

A `Fact` is the unit of VERIFIED information: it is produced only by backend
services/queries, carries its own source label, and is the only thing the LLM
is ever allowed to talk about.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_assistant.period import PeriodSpec


@dataclass
class Fact:
    key: str                                   # tool key e.g. "gst", "documents"
    title: str                                 # section heading
    lines: List[str] = field(default_factory=list)
    compact: Optional[str] = None              # one-line form used in multi-client answers
    available: bool = True                     # False => data missing / service failed
    note: Optional[str] = None                 # honest limitation or "no data" reason
    source: str = ""                           # human-readable provenance
    client_id: Optional[str] = None
    client_code: Optional[str] = None
    client_name: Optional[str] = None
    link: Optional[str] = None                 # in-app deep link for the source chip
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolContext:
    db: Session
    user: User
    period: PeriodSpec
    message: str
    today: date = field(default_factory=date.today)
    deadline: float = field(default_factory=lambda: time.monotonic() + 20.0)
    cache: Dict[Any, Any] = field(default_factory=dict)

    @property
    def out_of_time(self) -> bool:
        return time.monotonic() > self.deadline


# ── Formatting ────────────────────────────────────────────────────────────────

def to_decimal(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def inr(v: Any) -> str:
    """₹ with Indian digit grouping: 1,20,000.00"""
    d = to_decimal(v)
    if d is None:
        return "not available"
    d = d.quantize(Decimal("0.01"))
    sign = "-" if d < 0 else ""
    whole, frac = f"{abs(d):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts: List[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}₹{whole}.{frac}"


def fmt_date(d: Optional[date]) -> str:
    return d.strftime("%d %b %Y") if d else "—"


def client_link(code: Optional[str], tab: str) -> Optional[str]:
    return f"/app/workspace/{code}?tab={tab}" if code else None
