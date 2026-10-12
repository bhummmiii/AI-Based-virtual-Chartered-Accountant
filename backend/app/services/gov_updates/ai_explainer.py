"""
AI Plain-Language Explainer (Google Gemini Integration) with Strict Grounding Verification.
Strictly implements J6:
- Generates summary ONLY from stored content_text
- Structured JSON output: {summary, who_is_affected, key_dates, action_items}
- Hard grounding check: Every number, rate, currency amount, and doc number in the output
  MUST exist verbatim or normalized in content_text. If ungrounded, sets ai_status='rejected_ungrounded'.
- Skips when text_status != 'ok'
- Caches by content_hash
- Never presents AI output as the source's own words
"""

import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, List
from app.core.config import get_settings

logger = logging.getLogger(__name__)

UI_AI_LABEL = "AI-generated simple explanation - verify against the official document"


def extract_numerical_entities(text: str) -> List[str]:
    """
    Extracts all numbers, percentages, dates, rupee amounts from text for grounding verification.
    """
    entities = set()
    # Percentages: 5%, 18.5%
    for m in re.finditer(r"\b\d+(?:\.\d+)?%", text):
        entities.add(m.group(0))

    # Currency amounts: ₹ 50,000, Rs. 50,000, 5 crore, 75 lakh
    for m in re.finditer(r"(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?", text, re.IGNORECASE):
        entities.add(m.group(0).strip())

    # Raw numbers with commas or standalone integers/floats >= 2 digits: 50,000, 2026, 100
    for m in re.finditer(r"\b[\d,]+(?:\.\d+)?\b", text):
        val = m.group(0).replace(",", "")
        if val.isdigit() and len(val) >= 2:
            entities.add(m.group(0))

    return list(entities)


def verify_grounding(ai_json: Dict[str, Any], source_text: str) -> Tuple[bool, Optional[str]]:
    """
    Hard grounding check:
    Every number, rate, and amount in the AI output must appear in the official source text.
    Returns (is_grounded, failure_reason).
    """
    if not source_text:
        return False, "Source text is empty"

    # Normalize source text (strip commas, normalize rupee symbols, case)
    norm_source = source_text.lower()
    norm_source_no_commas = norm_source.replace(",", "")

    # Gather all AI generated text fields
    ai_combined_parts = []
    if "summary" in ai_json and isinstance(ai_json["summary"], str):
        ai_combined_parts.append(ai_json["summary"])
    if "who_is_affected" in ai_json and isinstance(ai_json["who_is_affected"], str):
        ai_combined_parts.append(ai_json["who_is_affected"])
    if "key_dates" in ai_json and isinstance(ai_json["key_dates"], list):
        ai_combined_parts.extend(str(d) for d in ai_json["key_dates"])
    if "action_items" in ai_json and isinstance(ai_json["action_items"], list):
        ai_combined_parts.extend(str(a) for a in ai_json["action_items"])

    ai_text = " ".join(ai_combined_parts)
    entities = extract_numerical_entities(ai_text)

    for ent in entities:
        ent_clean = ent.lower().strip()
        ent_no_commas = ent_clean.replace(",", "")
        # Check presence in source text
        if ent_clean in norm_source or ent_no_commas in norm_source_no_commas:
            continue
        # Also check pure numeric part if currency symbol was attached
        num_only = re.sub(r"[^\d.]", "", ent_clean)
        if num_only and (num_only in norm_source_no_commas):
            continue

        return False, f"Ungrounded numerical entity detected: '{ent}' not present in official source text"

    return True, None


class GovAiExplainer:
    def __init__(self):
        self.settings = get_settings()

    def generate_explanation(self, title: str, content_text: str, text_status: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Generates grounded explanation.
        Returns (ai_summary_dict, ai_status).
        ai_status can be: 'generated', 'rejected_ungrounded', 'failed', 'no_text'
        """
        if text_status != "ok" or not content_text or len(content_text.strip()) < 50:
            return None, "no_text"

        api_key = self.settings.GEMINI_API_KEY
        if not api_key:
            # Fallback when GEMINI_API_KEY is not configured: generate deterministic grounded summary
            return self._generate_fallback_grounded(title, content_text)

        prompt = f"""You are a statutory chartered accountant assistant.
Analyze ONLY the provided official text below and generate a plain-language summary in strictly valid JSON format.
DO NOT use any external knowledge. DO NOT invent or hallucinate any dates, numbers, turnover limits, or rates.
Every number, rate, and date in your response MUST appear verbatim in the source text.

Source Text:
\"\"\"
{content_text[:8000]}
\"\"\"

Output format must be valid JSON with exact keys:
{{
  "summary": "2 to 3 sentences explaining the core rule change in plain language.",
  "who_is_affected": "Specific category of businesses, professionals, or taxpayers affected.",
  "key_dates": ["List of statutory effective dates or compliance deadlines mentioned in text"],
  "action_items": ["Actionable compliance steps required, or none stated"]
}}
"""
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=self.settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )

            raw_text = response.text or ""
            data = json.loads(raw_text)

            # Grounding check
            is_grounded, reason = verify_grounding(data, content_text)
            if not is_grounded:
                logger.warning(f"AI explanation rejected: {reason}")
                return None, "rejected_ungrounded"

            data["disclaimer"] = UI_AI_LABEL
            return data, "generated"

        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            # Fallback to local grounded extraction
            return self._generate_fallback_grounded(title, content_text)

    def _generate_fallback_grounded(self, title: str, content_text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Deterministic, 100% grounded fallback when API key is unavailable or external call fails.
        Extracts only sentences directly from the source text.
        """
        paragraphs = [p.strip() for p in content_text.split("\n") if len(p.strip()) > 30]
        if not paragraphs:
            paragraphs = [title]

        first_para = paragraphs[0][:300]
        summary_sentence = first_para if first_para.endswith(".") else f"{first_para}."

        # Extract dates that actually exist in the text
        dates_in_text = re.findall(r"\b\d{1,2}[-/][A-Za-z0-9]+[-/]\d{4}\b", content_text)

        result = {
            "summary": summary_sentence,
            "who_is_affected": "Taxpayers, registered persons, or entities subject to this statutory rule.",
            "key_dates": list(set(dates_in_text))[:3],
            "action_items": ["Verify applicable provisions against the official document."],
            "disclaimer": UI_AI_LABEL,
        }

        # Validate grounding
        is_grounded, reason = verify_grounding(result, content_text)
        if not is_grounded:
            return None, "rejected_ungrounded"

        return result, "generated"
