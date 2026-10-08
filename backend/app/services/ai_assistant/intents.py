"""
Deterministic intent detection.

Keyword/regex based on purpose — the intent decides WHICH verified tools run, so it
must be predictable, explainable and impossible to "hallucinate". The LLM is never
asked to pick tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

# ── Intent names ──────────────────────────────────────────────────────────────
GREETING = "greeting"
HELP = "help"
CLIENT_LIST = "client_list"
ATTENTION = "workspace_attention"      # which clients need attention / are risky / overdue
PROFILE = "client_profile"
DOCUMENTS = "documents"
INVOICE_LOOKUP = "invoice_lookup"
GST = "gst_summary"
ITC = "itc"
DISCREPANCIES = "discrepancies"
ACCOUNTING = "accounting"
COMPLIANCE = "compliance"
INSIGHTS = "insights"                  # overview / health summary
KNOWLEDGE = "knowledge"                # general CA / statutory question (no client data)
OUT_OF_SCOPE = "out_of_scope"

DATA_INTENTS = {
    PROFILE, DOCUMENTS, INVOICE_LOOKUP, GST, ITC, DISCREPANCIES,
    ACCOUNTING, COMPLIANCE, INSIGHTS,
}

MAX_DATA_INTENTS = 4

_RX = {
    GREETING: re.compile(
        r"^\s*(hi|hii+|hello|hey|namaste|good\s+(morning|afternoon|evening)|thanks?|thank\s+you|ok(ay)?|great|cool)\b[\s!.,]*$",
        re.I,
    ),
    HELP: re.compile(r"\b(what can you do|what do you do|help me|how (do|can) i use|capabilit|your features|what can i ask)\b", re.I),
    CLIENT_LIST: re.compile(
        r"\b(list|show|display|give)\b.{0,20}\bclients?\b|\bhow many clients\b|\bnumber of clients\b|"
        r"\ball (my )?clients\b.{0,15}\b(list|names?)\b|\bwho are my clients\b|\bclients (do i have|i have|in (my )?workspace)\b|"
        r"\bmy clients\b\W*$",
        re.I,
    ),
    ATTENTION: re.compile(
        r"\b(which|what|who)\b.{0,30}\bclients?\b|\bclients?\b.{0,30}\b(need|needs|require|requires|attention|urgent|overdue|"
        r"pending|risky|high[\s-]?risk|medium[\s-]?risk|low[\s-]?risk|priority|flagged|at risk)\b|"
        r"\b(needs?|require[sd]?) (my )?attention\b|\bhigh[\s-]?risk\b|\bmost urgent\b|\bpriorit(y|ies)\b",
        re.I,
    ),
    PROFILE: re.compile(
        r"\b(gstin|gst number|pan( number| no)?|contact( person| number| details)?|phone|mobile|email|address|located|"
        r"location|which state|client type|return frequency|filing frequency|billing cycle|profile|who is|"
        r"details? (of|about|for)|tell me about|information (on|about))\b",
        re.I,
    ),
    DOCUMENTS: re.compile(
        r"\b(invoices?|documents?|bills?|uploaded|uploads?|ocr|vendors?|suppliers?|customers?|sales records?|"
        r"purchase records?|cnote|dnote|e-?way|e-?invoice|verified|unverified|rejected|how many (invoices|documents|bills))\b",
        re.I,
    ),
    GST: re.compile(
        r"\b(gst|gstr[\s-]?\d?[a-z]?|output tax|tax liability|tax payable|net payable|cash payable|liability|cgst|sgst|igst|"
        r"outward|turnover|tax due|3b|gstr1)\b",
        re.I,
    ),
    ITC: re.compile(
        r"\b(itc|input tax credit|input credit|gstr[\s-]?2[ab]|2b|2a|unmatched|reconcil\w*|claimable|claim)\b",
        re.I,
    ),
    DISCREPANCIES: re.compile(
        r"\b(discrepanc\w*|mismatch\w*|duplicate\w*|errors?|issues?|anomal\w*|fraud\w*|suspicious|inconsisten\w*|"
        r"flags?|flagged|problems?|wrong|incorrect|red flags?|missing gstin|unposted|invalid|review before filing|risks?)\b",
        re.I,
    ),
    ACCOUNTING: re.compile(
        r"\b(trial balance|ledger|journal|journals|voucher|vouchers|p\s*&\s*l|p and l|profit|loss|balance sheet|revenue|"
        r"income|expenses?|accounting|books|assets|equity|cash flow|depreciation|sales total|purchases total|debit|credit)\b",
        re.I,
    ),
    COMPLIANCE: re.compile(
        r"\b(due dates?|deadlines?|overdue|filing status|filed|filings?|returns?|notices?|audits?|income tax|itr|tds|"
        r"advance tax|compliance|upcoming|calendar|when is|when are|when to file)\b",
        re.I,
    ),
    INSIGHTS: re.compile(
        r"\b(overview|summary|summari[sz]e|snapshot|health|score|insights?|overall|brief|analy[sz]e|analysis|"
        r"how is|how's|status of|review|report on|recommend\w*|suggest\w*)\b",
        re.I,
    ),
}

_KNOWLEDGE_START = re.compile(
    r"^\s*(what('s| is| are)|explain|define|difference between|how (is|are|to|do|does|can)|when (is|are|do|does)|"
    r"can (i|we|a)|is (it|there)|why|section\s+\d|meaning of|tell me (about|the)|rate of|which (form|section))\b",
    re.I,
)
_DOMAIN_TERMS = re.compile(
    r"\b(gst|gstr|itc|tds|tcs|itr|income tax|advance tax|audit|section\s*\d+[a-z]*|80c|80d|hsn|sac|e-?invoic\w*|e-?way|"
    r"companies act|roc|mca|pf|epf|esi|depreciation|capital gains?|regime|form\s*\d+|circular|notification|budget|"
    r"cbic|cbdt|reverse charge|rcm|composition|ledger|trial balance|balance sheet|p\s*&\s*l|accounting|journal)\b",
    re.I,
)
_UNSUPPORTED_CALC = re.compile(
    r"\b(compute|calculate|estimate|project|forecast|predict|how much (will|would)|work out)\b.{0,60}"
    r"\b(advance tax|income tax|tax liability for fy|tds|depreciation|capital gains?|80c|old regime|new regime|"
    r"itr|presumptive)\b",
    re.I,
)
# Words that show the user is asking about THEIR data rather than a concept.
_DATA_CUE = re.compile(
    r"\b(my|our|their|this client|that client|the client|client's|net|total|payable|pending|overdue|eligible|"
    r"claimable|current|latest|how much|how many|amount|balance|list|show me|status|filed|due)\b",
    re.I,
)
_ALL_CLIENTS = re.compile(
    r"\b(all|every|each|across|entire|whole|total)\b.{0,25}\b(clients?|workspace|portfolio)\b|"
    r"\b(clients?|workspace|portfolio)\b.{0,15}\b(wise|combined|together)\b|\bmy (entire )?(workspace|portfolio)\b",
    re.I,
)

# Invoice / document reference extraction ---------------------------------------
_INV_AFTER_WORD = re.compile(
    r"\b(?:invoice|inv|bill|cnote|dnote|credit\s+note|debit\s+note|document|voucher)\s*"
    r"(?:no\.?|number|num|#)?\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/_.]{1,40})",
    re.I,
)
_INV_BARE = re.compile(r"\b([A-Za-z]{1,8}[\-/][A-Za-z0-9\-/]*\d[A-Za-z0-9\-/]*)\b")


@dataclass
class IntentResult:
    intents: List[str] = field(default_factory=list)
    invoice_refs: List[str] = field(default_factory=list)
    wants_all_clients: bool = False
    unsupported_calc: bool = False
    knowledge_like: bool = False
    knowledge_question: bool = False   # clearly conceptual: "What is GSTR-3B?"

    @property
    def data_intents(self) -> List[str]:
        return [i for i in self.intents if i in DATA_INTENTS]


def _prep(text: str) -> str:
    t = (text or "").strip()
    # "credit note" / "debit note" are documents, not accounting terms.
    t = re.sub(r"\bcredit\s+notes?\b", "cnote", t, flags=re.I)
    t = re.sub(r"\bdebit\s+notes?\b", "dnote", t, flags=re.I)
    return t


def extract_invoice_refs(message: str, exclude: Optional[Set[str]] = None) -> List[str]:
    """Pull plausible invoice numbers (must contain a digit) from the message."""
    exclude_n = {re.sub(r"[^a-z0-9]", "", e.lower()) for e in (exclude or set())}
    refs: List[str] = []
    for rx in (_INV_AFTER_WORD, _INV_BARE):
        for m in rx.finditer(message or ""):
            tok = m.group(1).strip(" .,:;-/")
            if not tok or not any(ch.isdigit() for ch in tok):
                continue
            if re.fullmatch(r"20\d{2}(-\d{1,2})?", tok):          # a year / year-month, not an invoice
                continue
            if re.sub(r"[^a-z0-9]", "", tok.lower()) in exclude_n:  # a client code like C-1071
                continue
            if tok.upper() not in {r.upper() for r in refs}:
                refs.append(tok)
    return refs[:5]


def detect_intents(message: str, client_codes: Optional[Set[str]] = None) -> IntentResult:
    raw = (message or "").strip()
    text = _prep(raw)
    res = IntentResult()

    if _RX[GREETING].match(text):
        res.intents = [GREETING]
        return res
    if _RX[HELP].search(text):
        res.intents = [HELP]
        return res

    res.wants_all_clients = bool(_ALL_CLIENTS.search(text))
    res.unsupported_calc = bool(_UNSUPPORTED_CALC.search(text))
    res.invoice_refs = extract_invoice_refs(raw, exclude=client_codes)

    found: List[str] = []
    if _RX[CLIENT_LIST].search(text):
        found.append(CLIENT_LIST)
    if _RX[ATTENTION].search(text) and CLIENT_LIST not in found:
        found.append(ATTENTION)
    if res.invoice_refs:
        found.append(INVOICE_LOOKUP)

    for intent in (PROFILE, GST, ITC, DISCREPANCIES, ACCOUNTING, COMPLIANCE, DOCUMENTS, INSIGHTS):
        if intent == DOCUMENTS and INVOICE_LOOKUP in found:
            continue
        if _RX[intent].search(text):
            found.append(intent)

    # "tax liability" also touches recorded income-tax figures.
    if re.search(r"\btax liability\b", text, re.I) and COMPLIANCE not in found:
        found.append(COMPLIANCE)

    # Specific intents beat the generic overview.
    data = [i for i in found if i in DATA_INTENTS]
    if len(data) > 1 and INSIGHTS in data:
        found.remove(INSIGHTS)

    # Keep the answer focused.
    kept: List[str] = []
    data_count = 0
    for i in found:
        if i in DATA_INTENTS:
            if data_count >= MAX_DATA_INTENTS:
                continue
            data_count += 1
        kept.append(i)

    res.knowledge_like = bool(_KNOWLEDGE_START.match(text) and _DOMAIN_TERMS.search(text)) or (
        bool(_DOMAIN_TERMS.search(text)) and not kept
    )
    res.knowledge_question = bool(
        _KNOWLEDGE_START.match(text) and _DOMAIN_TERMS.search(text) and not _DATA_CUE.search(text)
        and not res.invoice_refs
    )
    res.intents = kept
    return res
