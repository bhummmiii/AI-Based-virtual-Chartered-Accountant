"""
Deterministic client-mention resolution.

Given a user's message and the list of clients in the user's workspace, work out
which client(s) the message is about — by client code (C-1071), GSTIN, PAN,
company name (with typo tolerance) or contact person.

Never guesses between equally good candidates: ties are reported as AMBIGUOUS so
the assistant can ask the user to pick one instead of answering for the wrong client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional, Set

from app.models.client import Client

# Corporate-form words that carry no identity ("oggy pvt ltd" == "oggy").
_NAME_NOISE = {
    "pvt", "private", "ltd", "limited", "llp", "inc", "co", "company", "corp",
    "corporation", "and", "the", "of", "m", "s", "ms", "mr", "mrs",
}
# Words that are too generic to identify a client on their own.
_GENERIC = {
    "technologies", "technology", "solutions", "enterprises", "enterprise", "exports",
    "export", "imports", "industries", "industry", "services", "service", "traders",
    "trading", "consultants", "consultancy", "systems", "group", "global", "india",
    "international", "associates", "agro", "infra", "retail", "foods", "textiles",
    "logistics", "pharma", "labs", "works", "gst", "tax", "client", "invoice", "invoices",
}
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_CODE_RE = re.compile(r"\bc[\s\-]?(\d{3,6})\b", re.IGNORECASE)

RESOLVED_MIN_SCORE = 0.7
STRONG_SCORE = 0.9


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def name_tokens(name: str) -> List[str]:
    toks = [t for t in tokenize(name) if t not in _NAME_NOISE]
    return toks or tokenize(name)


@dataclass
class Candidate:
    client: Client
    score: float
    matched: Set[str] = field(default_factory=set)
    via: str = "name"          # code | gstin | pan | name | contact


@dataclass
class Mention:
    candidates: List[Candidate]
    ambiguous: bool = False

    @property
    def best(self) -> Candidate:
        return self.candidates[0]


def _normalize_code(code: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (code or "").lower())


def _fuzzy_hit(token: str, msg_tokens: Set[str]) -> bool:
    if len(token) < 5:
        return False
    for m in msg_tokens:
        if len(m) >= 5 and abs(len(m) - len(token)) <= 2 and SequenceMatcher(None, token, m).ratio() >= 0.86:
            return True
    return False


def _score_client(client: Client, msg_tokens: Set[str], codes: Set[str],
                  gstins: Set[str], pans: Set[str]) -> Optional[Candidate]:
    # 1. Hard identifiers
    if _normalize_code(client.client_code) in codes:
        return Candidate(client, 1.0, {f"#code:{client.client_code}"}, "code")
    if client.gst_number and client.gst_number.strip().upper() in gstins:
        return Candidate(client, 1.0, {f"#gstin:{client.gst_number}"}, "gstin")
    if client.pan_number and client.pan_number.strip().upper() in pans:
        return Candidate(client, 1.0, {f"#pan:{client.pan_number}"}, "pan")

    # 2. Company name
    sig = name_tokens(client.company_name or "")
    best: Optional[Candidate] = None
    if sig:
        exact = {t for t in sig if t in msg_tokens and len(t) >= 2}
        fuzzy = {t for t in sig if t not in exact and _fuzzy_hit(t, msg_tokens)}
        matched = exact | fuzzy
        if matched and len(matched) == len(sig):
            score = 1.0 if not fuzzy else 0.92
            best = Candidate(client, score, set(matched), "name")
        elif matched and any(t not in _GENERIC and len(t) >= 3 for t in matched):
            score = 0.5 + 0.4 * (len(matched) / len(sig))     # partial: 0.5 .. 0.9
            best = Candidate(client, round(score, 3), set(matched), "name")

    # 3. Contact person (two or more name parts, all present)
    contact = [t for t in name_tokens(client.contact_person or "") if len(t) >= 2]
    if len(contact) >= 2 and all(t in msg_tokens for t in contact):
        c = Candidate(client, 0.8, set(contact), "contact")
        if best is None or c.score > best.score:
            best = c

    if best and best.score >= 0.5:
        return best
    return None


def resolve_mentions(message: str, clients: List[Client], limit: int = 5) -> List[Mention]:
    """
    Return the distinct client mentions found in `message`.

    Two clients matched by DIFFERENT parts of the message are two mentions
    ("compare oggy and nimbus"). Two clients matched by the SAME words with the
    same strength are one AMBIGUOUS mention ("technologies").
    """
    msg_tokens = set(tokenize(message))
    upper = (message or "").upper()
    codes = {"c" + m for m in _CODE_RE.findall(message or "")}
    gstins = set(_GSTIN_RE.findall(upper))
    pans = set(_PAN_RE.findall(upper))

    cands: List[Candidate] = []
    for c in clients:
        cand = _score_client(c, msg_tokens, codes, gstins, pans)
        if cand:
            cands.append(cand)
    cands.sort(key=lambda c: (-c.score, (c.client.company_name or "").lower()))

    mentions: List[Mention] = []
    used: Set[str] = set()
    for cand in cands:
        overlap = cand.matched & used
        if overlap:
            # Competes with an already accepted mention for the same words.
            for m in mentions:
                if (cand.matched & m.best.matched) and abs(cand.score - m.best.score) <= 0.05 \
                        and cand.client.id != m.best.client.id:
                    m.candidates.append(cand)
                    m.ambiguous = True
                    break
            continue
        mentions.append(Mention([cand]))
        used |= cand.matched
        if len(mentions) >= limit:
            break

    # A mention backed only by a weak partial match is accepted, but a hard
    # identifier (code/GSTIN/PAN) always wins over any ambiguity.
    for m in mentions:
        if m.best.via in ("code", "gstin", "pan"):
            m.candidates = [m.best]
            m.ambiguous = False
    return [m for m in mentions if m.best.score >= RESOLVED_MIN_SCORE or m.ambiguous]


_FOLLOWUP_RE = re.compile(
    r"\b(it|its|their|them|this client|that client|the client|same client|same one|"
    r"what about|and for|also|how about|more details|tell me more|elaborate|explain that)\b",
    re.IGNORECASE,
)


def looks_like_followup(message: str) -> bool:
    """True for pronoun / elliptical messages that rely on the previous turn's client."""
    msg = (message or "").strip()
    if _FOLLOWUP_RE.search(msg):
        return True
    return len(tokenize(msg)) <= 3
