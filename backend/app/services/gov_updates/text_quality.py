"""
Text Quality Scoring and Letter-Spaced Text Repair Engine (K7).
Evaluates document text quality:
- Detects and repairs letter-spaced PDF artifact text (e.g. "M E S S A G E   T h e")
- Scores single-character tokens ratio, printable characters, minimum length, and English character distribution
- Assigns text_status = 'ok' | 'unreadable' | 'no_text' | 'too_large'
"""

import re
from typing import Tuple, Dict, Any


def score_text_quality(text: str) -> Dict[str, Any]:
    if not text or not text.strip():
        return {
            "score": 0.0,
            "single_char_ratio": 1.0,
            "printable_ratio": 0.0,
            "ascii_ratio": 0.0,
            "length": 0,
            "is_letter_spaced": False,
            "is_acceptable": False,
        }

    raw = text.strip()
    length = len(raw)
    tokens = [t for t in re.split(r"\s+", raw) if t]
    total_tokens = len(tokens)

    if total_tokens == 0:
        return {
            "score": 0.0,
            "single_char_ratio": 1.0,
            "printable_ratio": 0.0,
            "ascii_ratio": 0.0,
            "length": length,
            "is_letter_spaced": False,
            "is_acceptable": False,
        }

    single_chars = sum(1 for t in tokens if len(t) == 1 and t.isalnum())
    single_char_ratio = single_chars / total_tokens

    printable = sum(1 for c in raw if c.isprintable() or c in "\n\r\t")
    printable_ratio = printable / length

    ascii_chars = sum(1 for c in raw if ord(c) < 128)
    ascii_ratio = ascii_chars / length

    is_letter_spaced = single_char_ratio >= 0.40 and length >= 40
    is_acceptable = (
        single_char_ratio <= 0.25
        and printable_ratio >= 0.90
        and ascii_ratio >= 0.70
        and length >= 50
    )

    return {
        "single_char_ratio": single_char_ratio,
        "printable_ratio": printable_ratio,
        "ascii_ratio": ascii_ratio,
        "length": length,
        "is_letter_spaced": is_letter_spaced,
        "is_acceptable": is_acceptable,
    }


def repair_letter_spaced_text(text: str) -> str:
    """
    Repairs letter-spaced PDF text (e.g. 'M E S S A G E   T h e   F i f t h' -> 'MESSAGE The Fifth').
    Distinguishes within-word single space from between-word multi-space.
    """
    if not text:
        return ""

    lines = text.split("\n")
    repaired_lines = []

    for line in lines:
        stripped = line.strip()
        tokens = [t for t in re.split(r"\s+", stripped) if t]
        if not tokens:
            repaired_lines.append("")
            continue

        single_count = sum(1 for t in tokens if len(t) == 1 and t.isalnum())
        if len(tokens) >= 4 and (single_count / len(tokens)) >= 0.40:
            # 1. Replace 2 or more spaces with a temporary word delimiter
            temp_line = re.sub(r"[ \t]{2,}", " ___WORD_SEP___ ", line)
            # 2. Collapse single spaces between single alphanumeric characters
            repaired_words = []
            for chunk in temp_line.split("___WORD_SEP___"):
                chunk_tokens = chunk.strip().split()
                if chunk_tokens and all(len(t) == 1 for t in chunk_tokens):
                    # All single characters: join together into one word
                    repaired_words.append("".join(chunk_tokens))
                else:
                    # Mixed: collapse single space between single chars
                    fixed = re.sub(r"(?<=\b[A-Za-z0-9]) (?=[A-Za-z0-9]\b)", "", chunk.strip())
                    repaired_words.append(fixed)

            cleaned_line = " ".join(repaired_words).strip()
            repaired_lines.append(cleaned_line)
        else:
            repaired_lines.append(line)

    return "\n".join(repaired_lines)


def evaluate_and_clean_document_text(text: str) -> Tuple[str, str]:
    """
    Evaluates text quality, attempts repair if letter-spaced, and returns (final_text, text_status).
    text_status in ('ok', 'unreadable', 'no_text')
    """
    if not text or not text.strip():
        return "", "no_text"

    metrics = score_text_quality(text)
    candidate_text = text

    if metrics["is_letter_spaced"]:
        repaired = repair_letter_spaced_text(text)
        rep_metrics = score_text_quality(repaired)
        if rep_metrics["is_acceptable"] or rep_metrics["single_char_ratio"] < metrics["single_char_ratio"]:
            candidate_text = repaired
            metrics = rep_metrics

    if metrics["is_acceptable"]:
        return candidate_text, "ok"

    if metrics["single_char_ratio"] > 0.40 or metrics["printable_ratio"] < 0.70:
        return candidate_text, "unreadable"

    return candidate_text, "ok" if metrics["length"] >= 30 else "no_text"
