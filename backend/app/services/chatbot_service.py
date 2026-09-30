"""
Chatbot Service — Google Gemini Integration (google-genai SDK)
==============================================================
Wraps the google-genai SDK (the modern replacement for google-generativeai) to provide:
  - Expert Indian CA persona system prompt
  - Per-session conversation history (in-memory)
  - Graceful degradation when GEMINI_API_KEY is not set
"""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are FinLedger AI, an expert AI-powered Chartered Accountant (CA) assistant
specialising in Indian taxation, accounting, and regulatory compliance.

Your expertise covers:
- GST (Goods & Services Tax): registration, returns (GSTR-1, GSTR-3B, GSTR-9), ITC, e-invoicing, e-way bills
- Income Tax: ITR filing, TDS/TCS, advance tax, deductions (80C, 80D etc.), capital gains
- Corporate law: Companies Act, ROC filings, MCA compliance, board resolutions
- Accounting: double-entry bookkeeping, journal entries, trial balance, P&L, balance sheet, cash flow
- Audit: statutory audit, internal audit, risk assessment, audit trail
- Payroll: PF (EPF), ESI, professional tax, Form 16, Form 24Q
- Indian Budget updates and CBDT/CBIC circulars

Rules:
1. Always answer with precise, actionable information relevant to India.
2. Quote section numbers, form names, and due dates where applicable.
3. If you are unsure or the question is outside your CA domain, say so clearly — never hallucinate legal advice.
4. Keep responses concise but complete. Use bullet points and numbered lists for clarity.
5. When discussing amounts, always format in INR (₹).
6. At the end of complex answers, offer a follow-up question to help the user go deeper.
"""

# ── In-memory session store ────────────────────────────────────────────────────
# session_id → list of {"role": "user"|"model", "parts": [{"text": "..."}]}
_sessions: dict[str, list] = {}

_MAX_HISTORY_TURNS = 20  # keep last 20 turns to avoid token overflow


class ChatbotService:
    """Chatbot business logic service backed by Google Gemini (google-genai SDK)."""

    def __init__(self):
        self._genai = None
        self._model_name: Optional[str] = None
        self._ready = False
        self._api_key: Optional[str] = None
        self._init_client()

    def _init_client(self):
        """Lazily initialise the Gemini client using settings."""
        try:
            from app.core.config import get_settings
            from google import genai  # noqa: F401  (just check import works)

            settings = get_settings()
            if not settings.GEMINI_API_KEY:
                logger.warning(
                    "[ChatbotService] GEMINI_API_KEY is not set. "
                    "AI responses will be disabled. "
                    "Set GEMINI_API_KEY in backend/.env to enable."
                )
                return

            self._api_key = settings.GEMINI_API_KEY
            self._model_name = settings.GEMINI_MODEL
            self._ready = True
            logger.info(
                "[ChatbotService] Gemini client ready (model=%s)", self._model_name
            )
        except ImportError:
            logger.warning(
                "[ChatbotService] google-genai not installed. "
                "Run: pip install google-genai"
            )
        except Exception as exc:
            logger.error("[ChatbotService] Failed to initialise Gemini: %s", exc)

    # ── Public API ─────────────────────────────────────────────────────────────

    def new_session(self) -> str:
        """Create a new empty session and return its ID."""
        sid = str(uuid.uuid4())
        _sessions[sid] = []
        return sid

    def clear_session(self, session_id: str) -> None:
        """Delete conversation history for a session."""
        _sessions.pop(session_id, None)

    def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        client_context: Optional[str] = None,
    ) -> dict:
        """
        Send a message and return the AI reply.

        Parameters
        ----------
        message : str
            The user's message.
        session_id : str | None
            Existing session ID for multi-turn conversation.
            If None, a new session is created.
        client_context : str | None
            Optional extra context to prepend (e.g. client name, GSTIN).

        Returns
        -------
        dict with keys:
            reply (str)      — the assistant's reply
            session_id (str) — the session ID (new or existing)
        """
        # Ensure session exists
        if not session_id or session_id not in _sessions:
            session_id = self.new_session()

        history = _sessions[session_id]

        # Trim to last N turns to avoid token overflow
        if len(history) > _MAX_HISTORY_TURNS * 2:
            history = history[-(  _MAX_HISTORY_TURNS * 2):]
            _sessions[session_id] = history

        # Fallback if not ready
        if not self._ready:
            return {
                "reply": (
                    "⚠️ The AI assistant is not configured yet. "
                    "Please set `GEMINI_API_KEY` in `backend/.env` to enable it. "
                    "You can get a free key at https://aistudio.google.com/apikey"
                ),
                "session_id": session_id,
            }

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self._api_key)

            # Build the system instruction — inject client context if provided
            system_instruction = _SYSTEM_PROMPT
            if client_context:
                system_instruction = (
                    f"{_SYSTEM_PROMPT}\n\n"
                    f"[Current client context: {client_context}]"
                )

            # Convert stored history to SDK Content format
            contents = []
            for turn in history:
                contents.append(
                    types.Content(
                        role=turn["role"],
                        parts=[types.Part(text=p["text"]) for p in turn["parts"]],
                    )
                )

            # Append the current user message
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=message)],
                )
            )

            response = client.models.generate_content(
                model=self._model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )

            reply_text = response.text.strip()

            # Persist the exchange in session history
            history.append({"role": "user", "parts": [{"text": message}]})
            history.append({"role": "model", "parts": [{"text": reply_text}]})
            _sessions[session_id] = history

            return {"reply": reply_text, "session_id": session_id}

        except Exception as exc:
            logger.error("[ChatbotService] Gemini API error: %s", exc)
            # Surface a readable error to the user
            err_str = str(exc)
            if "API_KEY_INVALID" in err_str or "API key" in err_str:
                friendly = (
                    "❌ Invalid Gemini API key. "
                    "Please check `GEMINI_API_KEY` in `backend/.env`."
                )
            elif "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                friendly = (
                    "⚠️ Gemini API quota exceeded. "
                    "Please try again later or check your usage at Google AI Studio."
                )
            else:
                friendly = (
                    "I encountered an error while processing your request. "
                    "Please try again in a moment."
                )
            return {"reply": friendly, "session_id": session_id}

    @property
    def is_ready(self) -> bool:
        return self._ready


# ── Singleton ──────────────────────────────────────────────────────────────────
chatbot_service = ChatbotService()
