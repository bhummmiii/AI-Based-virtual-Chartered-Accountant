"""
FinLedger AI Assistant Engine
=============================
Unified intelligence engine powering BOTH:
  1. Smaller Module: Client AI Insights & Client Chat (scoped strictly to one client)
  2. Bigger Module: Global AI Assistant (sidebar: full workspace scope, cross-client access)

Architecture (Deterministic Tool-First Grounding):
  Question -> Intent & Period Detection -> Tool Dispatch -> Verified Facts
  -> Grounded LLM Explanation (or Deterministic Fallback) -> Guard Rails -> Answer + Sources
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.client import Client
from app.models.user import User
from app.services.ai_assistant.facts import Fact, ToolContext, inr
from app.services.ai_assistant.guard import (
    build_deterministic_fallback,
    verify_response_safety,
)
from app.services.ai_assistant.intents import (
    ACCOUNTING,
    ATTENTION,
    CLIENT_LIST,
    COMPLIANCE,
    DISCREPANCIES,
    DOCUMENTS,
    GREETING,
    HELP,
    INSIGHTS,
    INVOICE_LOOKUP,
    ITC,
    KNOWLEDGE,
    PROFILE,
    GST,
    detect_intents,
)
from app.services.ai_assistant.period import PeriodSpec, parse_period
from app.services.ai_assistant.resolver import (
    looks_like_followup,
    resolve_mentions,
)
from app.services.ai_assistant.tools import (
    aggregate_totals,
    run_per_client,
    tool_accounting,
    tool_compliance,
    tool_discrepancies,
    tool_documents,
    tool_insights,
    tool_invoice_lookup,
    tool_itc,
    tool_profile,
    tool_gst,
    tool_workspace_attention,
    tool_workspace_list,
)

logger = logging.getLogger(__name__)

# System prompt for LLM explaining verified facts
_GROUNDED_SYSTEM_PROMPT = """You are FinLedger AI, an expert AI Chartered Accountant assistant for Indian taxation and accounting.

CRITICAL NON-NEGOTIABLE RULES:
1. You must ONLY answer using the VERIFIED FACTS provided below in the prompt.
2. DO NOT invent, hallucinate, extrapolate, or estimate any financial figures, invoices, dates, or clients.
3. If data is marked as unavailable or missing, clearly state that it is not available in the records.
4. When discussing amounts, always format in Indian Rupee format (₹).
5. Quote statutory references (CGST Act, Income Tax Act, ICAI standards) where relevant.
6. Provide structured, executive-level summaries with bullet points and bold key figures.
7. Be concise, direct, professional, and never provide illegal tax evasion advice.
"""

# In-memory session store: session_id -> { "history": [...], "last_client_id": str }
_sessions: Dict[str, Dict[str, Any]] = {}
_MAX_HISTORY_TURNS = 20


@dataclass
class EngineResult:
    reply: str
    session_id: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    client_context: Optional[Dict[str, Any]] = None
    data_available: bool = True


class AssistantEngine:
    """The central assistant engine for FinLedger."""

    def __init__(self):
        self._ready = False
        self._model_name = "gemini-flash-lite-latest"
        self._api_key: Optional[str] = None
        self._init_gemini()

    def _init_gemini(self):
        """Check if Gemini credentials are present."""
        try:
            settings = get_settings()
            if settings.GEMINI_API_KEY:
                self._api_key = settings.GEMINI_API_KEY
                self._model_name = settings.GEMINI_MODEL
                self._ready = True
                logger.info("[AssistantEngine] Gemini configured (model=%s)", self._model_name)
        except Exception as exc:
            logger.warning("[AssistantEngine] Gemini initialization warning: %s", exc)

    def new_session(self) -> str:
        sid = str(uuid.uuid4())
        _sessions[sid] = {"history": [], "last_client_id": None}
        return sid

    def clear_session(self, session_id: str) -> None:
        _sessions.pop(session_id, None)

    # ── Client Scope Helper ───────────────────────────────────────────────────

    def _get_user_clients(self, db: Session, user: User) -> List[Client]:
        """Fetch all active clients accessible by the current user."""
        q = db.query(Client).filter(Client.status != "deleted")
        if user.role != "admin":
            q = q.filter(Client.user_id == user.id)
        return q.all()

    def _find_client_by_id_or_code(
        self, db: Session, user: User, client_identifier: str
    ) -> Optional[Client]:
        """Lookup client by UUID or client_code (e.g. 'C-1071')."""
        clean = client_identifier.strip()
        # 1. Try UUID
        try:
            uid = uuid.UUID(clean)
            q = db.query(Client).filter(Client.id == uid, Client.status != "deleted")
            if user.role != "admin":
                q = q.filter(Client.user_id == user.id)
            c = q.first()
            if c:
                return c
        except ValueError:
            pass

        # 2. Try client_code
        q = db.query(Client).filter(
            Client.client_code.ilike(clean), Client.status != "deleted"
        )
        if user.role != "admin":
            q = q.filter(Client.user_id == user.id)
        return q.first()

    # ── Main Entrypoint ───────────────────────────────────────────────────────

    def process_query(
        self,
        db: Session,
        user: User,
        message: str,
        session_id: Optional[str] = None,
        explicit_client_id: Optional[str] = None,
        period_override: Optional[str] = None,
    ) -> EngineResult:
        """
        Process user query across client scope or workspace scope.
        """
        if not session_id or session_id not in _sessions:
            session_id = self.new_session()

        session_data = _sessions[session_id]
        history = session_data["history"]

        # Parse period & intents
        all_clients = self._get_user_clients(db, user)
        client_codes = {c.client_code for c in all_clients if c.client_code}
        intent_res = detect_intents(message, client_codes=client_codes)
        period_spec = parse_period(period_override) if period_override else parse_period(message)

        # 1. Quick greetings & Help intents
        if intent_res.intents == [GREETING]:
            reply = (
                "Hello! 👋 I am **FinLedger AI**, your Chartered Accountant assistant. "
                "I have verified access to your workspace accounting, invoices, and GST records. "
                "How can I help you today?"
            )
            return EngineResult(reply=reply, session_id=session_id)

        if intent_res.intents == [HELP]:
            reply = (
                "Here are the ways I can assist you across your clients and workspace:\n\n"
                "• **Client Overview & Status**: *'Tell me about Oggy Pvt Ltd'* or *'Client profile of C-1071'*\n"
                "• **GST & GSTR-3B Calculation**: *'What is the net GST payable for Coastal Exports for July 2026?'*\n"
                "• **Input Tax Credit (ITC)**: *'Show ITC eligible vs booked in ledger for Vikram Singh'*\n"
                "• **Discrepancy Audit**: *'Find any invoice discrepancies or tax mismatches for Nimbus Technologies'*\n"
                "• **Accounting & Trial Balance**: *'Is the trial balance balanced for Oggy Pvt Ltd?'*\n"
                "• **Compliance Calendar**: *'When is the next GSTR-3B due date?'*\n"
                "• **Workspace Monitoring**: *'Which clients need urgent attention?'* or *'List all high-risk clients'*\n"
                "• **Statutory & Tax Rules**: *'Explain Section 16(2)(aa) of the CGST Act simply'*"
            )
            return EngineResult(reply=reply, session_id=session_id)

        # 2. Resolve Client Scope
        target_clients: List[Client] = []
        is_client_specific = False

        if explicit_client_id:
            # Mode A: Small module inside Client Workspace
            matched = self._find_client_by_id_or_code(db, user, explicit_client_id)
            if matched:
                target_clients = [matched]
                is_client_specific = True
                session_data["last_client_id"] = str(matched.id)
        else:
            # Mode B: Global Assistant in Sidebar
            mentions = resolve_mentions(message, all_clients)

            if mentions:
                # Check for ambiguity
                first_mention = mentions[0]
                if first_mention.ambiguous and len(first_mention.candidates) > 1:
                    candidates_str = ", ".join(
                        f"**{c.client.company_name}** ({c.client.client_code})"
                        for c in first_mention.candidates[:4]
                    )
                    return EngineResult(
                        reply=f"Multiple clients match your query: {candidates_str}. "
                              f"Please specify which client you are referring to.",
                        session_id=session_id,
                    )
                # Take all distinct mentioned clients (allows comparisons e.g. 'compare A and B')
                target_clients = [m.best.client for m in mentions]
                is_client_specific = True
                session_data["last_client_id"] = str(target_clients[0].id)
            elif looks_like_followup(message) and session_data.get("last_client_id"):
                # Recall client from previous turn in this session
                prior_client = self._find_client_by_id_or_code(
                    db, user, session_data["last_client_id"]
                )
                if prior_client:
                    target_clients = [prior_client]
                    is_client_specific = True

        # 3. Handle Workspace-level intents if no specific client is targeted
        facts: List[Fact] = []
        ctx = ToolContext(
            db=db,
            user=user,
            period=period_spec,
            message=message,
            today=date.today(),
        )

        if not is_client_specific:
            # User wants workspace overview, client listing, or attention items
            if CLIENT_LIST in intent_res.intents or not intent_res.data_intents:
                if ATTENTION in intent_res.intents:
                    facts.append(tool_workspace_attention(ctx, all_clients))
                elif CLIENT_LIST in intent_res.intents:
                    facts.append(tool_workspace_list(ctx, all_clients))
                elif intent_res.knowledge_like or intent_res.knowledge_question:
                    # Conceptual CA query (e.g., "What is GSTR-3B?")
                    return self._answer_knowledge_query(message, session_id, history)
                else:
                    # General workspace summary
                    facts.append(tool_workspace_attention(ctx, all_clients))
            elif ATTENTION in intent_res.intents:
                facts.append(tool_workspace_attention(ctx, all_clients))
            elif intent_res.wants_all_clients and all_clients:
                # Aggregation across all clients for GST, Discrepancies, etc.
                facts.extend(self._run_workspace_aggregations(ctx, all_clients, intent_res.intents))
            else:
                # User asked a client-oriented question without specifying client name
                if intent_res.knowledge_question:
                    return self._answer_knowledge_query(message, session_id, history)

                return EngineResult(
                    reply=(
                        "Which client would you like me to check? "
                        "Please provide the client name, client code (e.g. `C-1071`), or GSTIN. "
                        "Alternatively, ask *'Which clients need attention?'* for a workspace overview."
                    ),
                    session_id=session_id,
                )
        else:
            # 4. Client-Specific Tool Execution
            for client in target_clients:
                client_facts = self._run_client_tools(
                    ctx=ctx,
                    client=client,
                    intents=intent_res.intents,
                    invoice_refs=intent_res.invoice_refs,
                )
                facts.extend(client_facts)

        # 5. Generate Grounded Response
        reply = self._generate_grounded_reply(
            message=message,
            facts=facts,
            history=history,
            target_clients=target_clients,
        )

        # 6. Safety & Anti-Hallucination Guard
        is_safe, reason = verify_response_safety(reply, facts)
        if not is_safe:
            logger.warning("[AssistantEngine] Guard triggered fallback: %s", reason)
            reply = build_deterministic_fallback(facts, message)

        # 7. Record History
        history.append({"role": "user", "text": message})
        history.append({"role": "model", "text": reply})
        if len(history) > _MAX_HISTORY_TURNS * 2:
            session_data["history"] = history[-_MAX_HISTORY_TURNS * 2 :]

        # 8. Extract Sources & Structured Metadata
        sources = []
        for f in facts:
            if f.source:
                sources.append({
                    "title": f.title,
                    "source": f.source,
                    "link": f.link,
                    "client_code": f.client_code,
                    "available": f.available,
                })

        client_meta = None
        if target_clients and len(target_clients) == 1:
            c = target_clients[0]
            client_meta = {
                "id": str(c.id),
                "code": c.client_code,
                "name": c.company_name,
                "gstin": c.gst_number,
                "risk": c.risk_level,
            }

        return EngineResult(
            reply=reply,
            session_id=session_id,
            sources=sources,
            client_context=client_meta,
            data_available=any(f.available for f in facts) if facts else True,
        )

    # ── Tool Dispatcher ───────────────────────────────────────────────────────

    def _run_client_tools(
        self,
        ctx: ToolContext,
        client: Client,
        intents: List[str],
        invoice_refs: List[str],
    ) -> List[Fact]:
        """Dispatch relevant verified tools for a specific client."""
        facts: List[Fact] = []

        if invoice_refs:
            facts.append(tool_invoice_lookup(ctx, client, invoice_refs))

        # If no specific data intents were triggered, provide an insightful overview
        data_intents = [i for i in intents if i in {
            PROFILE, DOCUMENTS, GST, ITC, DISCREPANCIES, ACCOUNTING, COMPLIANCE, INSIGHTS
        }]

        if not data_intents and not invoice_refs:
            # Default rich client overview
            facts.append(tool_profile(ctx, client))
            facts.append(tool_insights(ctx, client))
            facts.append(tool_gst(ctx, client))
            facts.append(tool_discrepancies(ctx, client))
            return facts

        if PROFILE in intents:
            facts.append(tool_profile(ctx, client))
        if DOCUMENTS in intents:
            facts.append(tool_documents(ctx, client))
        if GST in intents:
            facts.append(tool_gst(ctx, client))
        if ITC in intents:
            facts.append(tool_itc(ctx, client))
        if DISCREPANCIES in intents:
            facts.append(tool_discrepancies(ctx, client))
        if ACCOUNTING in intents:
            facts.append(tool_accounting(ctx, client))
        if COMPLIANCE in intents:
            facts.append(tool_compliance(ctx, client))
        if INSIGHTS in intents:
            facts.append(tool_insights(ctx, client))

        return facts

    def _run_workspace_aggregations(
        self, ctx: ToolContext, clients: List[Client], intents: List[str]
    ) -> List[Fact]:
        """Run tool across all clients and aggregate verified figures."""
        facts: List[Fact] = []
        if GST in intents:
            client_facts, _ = run_per_client(ctx, tool_gst, clients)
            agg = aggregate_totals(client_facts, "gst")
            if agg:
                facts.append(agg)
            facts.extend(client_facts[:5])
        elif DISCREPANCIES in intents:
            client_facts, _ = run_per_client(ctx, tool_discrepancies, clients)
            agg = aggregate_totals(client_facts, "discrepancies")
            if agg:
                facts.append(agg)
            facts.extend([f for f in client_facts if f.data.get("total", 0) > 0][:5])
        elif DOCUMENTS in intents:
            client_facts, _ = run_per_client(ctx, tool_documents, clients)
            agg = aggregate_totals(client_facts, "documents")
            if agg:
                facts.append(agg)
            facts.extend(client_facts[:5])
        else:
            facts.append(tool_workspace_attention(ctx, clients))

        return facts

    # ── LLM Generation & Grounding ────────────────────────────────────────────

    def _generate_grounded_reply(
        self,
        message: str,
        facts: List[Fact],
        history: List[Dict[str, str]],
        target_clients: List[Client],
    ) -> str:
        """Call Gemini to explain verified facts, or return deterministic fallback."""
        if not self._ready or not self._api_key:
            # Seamless deterministic fallback when Gemini API key is not present
            return build_deterministic_fallback(facts, message)

        try:
            from google import genai
            from google.genai import types

            client_sdk = genai.Client(api_key=self._api_key)

            # Build facts text block
            facts_block_lines = []
            for f in facts:
                client_tag = f" [{f.client_name} ({f.client_code})]" if f.client_code else ""
                facts_block_lines.append(f"--- FACT: {f.title}{client_tag} ---")
                facts_block_lines.append(f"Source: {f.source}")
                if not f.available:
                    facts_block_lines.append(f"Status: UNAVAILABLE ({f.note or 'no data'})")
                else:
                    for line in f.lines:
                        facts_block_lines.append(f"  {line}")
                facts_block_lines.append("")

            facts_text = "\n".join(facts_block_lines)

            system_instruction = (
                f"{_GROUNDED_SYSTEM_PROMPT}\n\n"
                f"[VERIFIED CLIENT / WORKSPACE FACTS]:\n{facts_text}\n\n"
                f"REMINDER: Quote EXACT amounts from facts above. Never hallucinate or add any other figures."
            )

            # Convert previous turns
            sdk_contents = []
            for turn in history[-6:]:  # last 3 turns
                sdk_contents.append(
                    types.Content(
                        role=turn["role"],
                        parts=[types.Part(text=turn["text"])],
                    )
                )

            sdk_contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=message)],
                )
            )

            response = client_sdk.models.generate_content(
                model=self._model_name,
                contents=sdk_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,  # Low temperature for strict factual accuracy
                    max_output_tokens=2048,
                ),
            )

            reply = response.text.strip()
            return reply

        except Exception as exc:
            logger.warning("[AssistantEngine] Gemini call failed (%s), using deterministic fallback", exc)
            return build_deterministic_fallback(facts, message)

    def _answer_knowledge_query(
        self, message: str, session_id: str, history: List[Dict[str, str]]
    ) -> EngineResult:
        """Answer purely statutory / CA domain questions."""
        if not self._ready or not self._api_key:
            reply = (
                "For Indian tax and regulatory queries, please ensure `GEMINI_API_KEY` is configured in `backend/.env`. "
                "You can ask about GST rules, e-invoicing limits, ITR sections, or company compliance."
            )
            return EngineResult(reply=reply, session_id=session_id)

        try:
            from google import genai
            from google.genai import types

            client_sdk = genai.Client(api_key=self._api_key)
            system_prompt = (
                "You are FinLedger AI, an expert Chartered Accountant in Indian corporate tax, GST, and accounting standards. "
                "Answer the user's statutory or technical question clearly, citing relevant sections of the CGST Act, "
                "Income Tax Act 1961, or Companies Act 2013 where applicable. Do not discuss any fictional client data."
            )

            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part(text=message)],
                )
            ]

            resp = client_sdk.models.generate_content(
                model=self._model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3,
                    max_output_tokens=1500,
                ),
            )
            reply = resp.text.strip()
            history.append({"role": "user", "text": message})
            history.append({"role": "model", "text": reply})
            return EngineResult(reply=reply, session_id=session_id)
        except Exception as exc:
            logger.error("[AssistantEngine] Knowledge query error: %s", exc)
            return EngineResult(
                reply="I encountered an error answering this tax query. Please try again in a moment.",
                session_id=session_id,
            )


# ── Global Singleton ──────────────────────────────────────────────────────────
assistant_engine = AssistantEngine()
