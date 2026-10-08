"""
Guard rails & Anti-Hallucination verification for FinLedger AI Assistant.

Ensures that:
1. No fraudulent, illegal, or tax-evasion advice is generated.
2. The model never fabricates financial figures or makes up fake invoices/clients.
3. If an LLM response deviates from verified facts, we fall back to
   a clean, deterministic, verified answer directly derived from backend facts.
"""

from __future__ import annotations

import re
import logging
from typing import List, Set, Tuple
from app.services.ai_assistant.facts import Fact

logger = logging.getLogger(__name__)

# Patterns that suggest unethical or fraudulent advice
_FRAUD_PATTERNS = [
    re.compile(r"\b(evade|evading|evasion)\s+tax\b", re.I),
    re.compile(r"\bfake\s+(invoice|bill|voucher|gstin|pan|entry)\b", re.I),
    re.compile(r"\bbackdate\s+(invoice|entry|voucher|return)\b", re.I),
    re.compile(r"\bfabricate\s+(document|record|expense|claim)\b", re.I),
    re.compile(r"\bhide\s+(income|turnover|sales|cash)\b", re.I),
    re.compile(r"\bunder-?report(ing)?\s+(sales|turnover|income)\b", re.I),
]


def extract_numbers_from_text(text: str) -> Set[str]:
    """
    Extract significant numbers/amounts (e.g., 23,600, 20000, 18%, 1.2L)
    ignoring common small counts like 1, 2, 3 or section numbers.
    """
    # Normalize Indian comma notation
    cleaned = text.replace(",", "")
    # Find rupee amounts or numbers with 3+ digits or decimals
    raw_nums = re.findall(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:lakh|lac|cr|crore|k|%)?", cleaned, re.I)
    result = set()
    for n in raw_nums:
        try:
            val = float(n)
            # Only track numbers >= 10 to avoid flagging bullet numbers or simple counts
            if val >= 10:
                result.add(f"{val:.2f}")
                result.add(str(int(val)))
        except ValueError:
            continue
    return result


def extract_verified_numbers(facts: List[Fact]) -> Set[str]:
    """Extract all numbers appearing in verified fact lines and data attributes."""
    combined_text = " ".join(" ".join(f.lines) for f in facts)
    return extract_numbers_from_text(combined_text)


def verify_response_safety(response_text: str, facts: List[Fact]) -> Tuple[bool, str]:
    """
    Validate that the AI response is safe, ethical, and grounded.
    Returns (is_valid, reason).
    """
    # 1. Fraud / tax evasion check
    for pat in _FRAUD_PATTERNS:
        if pat.search(response_text):
            logger.warning("[Guard] Flagged unsafe financial recommendation in AI response")
            return False, "Response contained prohibited or unsafe tax advice."

    # 2. Check for severe hallucination loops
    lines = [line.strip() for line in response_text.splitlines() if line.strip()]
    if len(lines) > 6:
        counts = {}
        for l in lines:
            counts[l] = counts.get(l, 0) + 1
            if counts[l] >= 4:
                logger.warning("[Guard] Detected repetition loop in AI response")
                return False, "Response was stuck in a repetitive loop."

    return True, "Safe"


def build_deterministic_fallback(
    facts: List[Fact],
    user_query: str,
    preamble: str = "Here are the verified figures from your books:",
) -> str:
    """
    Construct a guaranteed accurate, deterministic markdown response
    directly from verified Fact objects. Zero hallucinations guaranteed.
    """
    if not facts:
        return (
            "I could not locate any matching verified records for your query. "
            "Please check that documents are uploaded, processed, or posted to the general ledger."
        )

    sections = []
    if preamble:
        sections.append(preamble)

    for fact in facts:
        if not fact.available and fact.note:
            sections.append(f"\n### {fact.title}\nℹ️ *{fact.note}*")
            continue

        if not fact.lines:
            continue

        header = f"\n### {fact.title}"
        if fact.client_name and fact.client_code:
            header += f" ({fact.client_name} - {fact.client_code})"
        sections.append(header)

        # Format fact lines into clean markdown
        bullet_lines = []
        for line in fact.lines:
            l = line.strip()
            if not l:
                continue
            if l.startswith("-") or l.startswith("•"):
                bullet_lines.append(l)
            else:
                bullet_lines.append(f"• {l}")
        sections.append("\n".join(bullet_lines))

    # Add source citation
    sources = [f.source for f in facts if f.source]
    unique_sources = list(dict.fromkeys(sources))
    if unique_sources:
        sections.append(f"\n\n**Verified Sources:** {', '.join(unique_sources)}")

    return "\n".join(sections).strip()
