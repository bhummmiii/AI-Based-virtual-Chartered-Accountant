"""
Chatbot API Router
==================
POST   /api/v1/chatbot/chat                        — send a message, get AI reply
GET    /api/v1/chatbot/session/new                  — create a new session ID
DELETE /api/v1/chatbot/session/{session_id}         — clear conversation history
GET    /api/v1/chatbot/status                       — check if Gemini is configured
GET    /api/v1/chatbot/insights/{client_id}         — backend-grounded AI insights for a client
POST   /api/v1/chatbot/chat-with-context            — chat enriched with verified client context
GET    /api/v1/chatbot/resolve-client               — resolve client name/GSTIN → client_id
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Optional, List
import uuid

from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.chatbot_service import chatbot_service
from app.database.session import get_db
from sqlalchemy.orm import Session

router = APIRouter()


# ── Request / Response Schemas ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    session_id: Optional[str] = Field(None, description="Existing session ID for multi-turn chat")
    client_context: Optional[str] = Field(None, description="Optional client info for context")
    client_id: Optional[str] = Field(None, description="Optional client UUID to explicitly scope chat")


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sources: Optional[List[dict]] = None
    client_context: Optional[dict] = None
    data_available: bool = True


class SessionResponse(BaseModel):
    session_id: str


class StatusResponse(BaseModel):
    ready: bool
    model: str
    message: str


class ContextualChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None
    client_id: Optional[str] = Field(None, description="Client UUID for context enrichment")
    period: Optional[str] = Field(None, description="Period e.g. '2026-07' or 'Q2 FY 2026-27'")


class AIInsightItem(BaseModel):
    id: int
    text: str
    severity: str   # "danger" | "warning" | "success" | "info"
    source: str     # always "backend" — never "mock"


class AIInsightsResponse(BaseModel):
    client_id: str
    client_name: str
    period: Optional[str]
    insights: List[AIInsightItem]
    data_available: bool
    message: str


class ClientMatch(BaseModel):
    client_id: str
    name: str
    gstin: Optional[str]
    client_code: str


class ClientResolveResponse(BaseModel):
    matches: List[ClientMatch]
    ambiguous: bool
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse, summary="Send a message to the AI CA assistant")
async def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Multi-turn chat with the AI Chartered Accountant across the entire workspace.

    - Resolves any client mentioned by name, code (C-1071), GSTIN, or PAN.
    - Can answer across all clients or specific clients.
    - Grounded in verified database tools; zero hallucinated figures.
    """
    if not body.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message cannot be empty",
        )

    try:
        from app.services.ai_assistant.engine import assistant_engine
        result = assistant_engine.process_query(
            db=db,
            user=current_user,
            message=body.message.strip(),
            session_id=body.session_id,
            explicit_client_id=body.client_id,
        )
        return ChatResponse(
            reply=result.reply,
            session_id=result.session_id,
            sources=result.sources,
            client_context=result.client_context,
            data_available=result.data_available,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[ChatbotRouter] assistant_engine fallback in /chat: %s", exc)
        res = chatbot_service.chat(
            message=body.message.strip(),
            session_id=body.session_id,
            client_context=body.client_context,
        )
        return ChatResponse(**res)


@router.post(
    "/chat-with-context",
    response_model=ChatResponse,
    summary="Chat enriched with verified backend client context",
)
async def chat_with_context(
    body: ContextualChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Client-scoped AI Assistant chat (Smaller module in Client Workspace).

    Strictly grounded in verified backend services for the specific client.
    Guarantees no hallucination or numerical fabrication.
    """
    if not body.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message cannot be empty",
        )

    try:
        from app.services.ai_assistant.engine import assistant_engine
        result = assistant_engine.process_query(
            db=db,
            user=current_user,
            message=body.message.strip(),
            session_id=body.session_id,
            explicit_client_id=body.client_id,
            period_override=body.period,
        )
        return ChatResponse(
            reply=result.reply,
            session_id=result.session_id,
            sources=result.sources,
            client_context=result.client_context,
            data_available=result.data_available,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[ChatbotRouter] assistant_engine fallback in /chat-with-context: %s", exc)
        client_context_text: Optional[str] = None
        if body.client_id:
            try:
                from app.services.ai_context_service import (
                    build_client_context,
                    build_context_prompt_fragment,
                )
                cid = uuid.UUID(body.client_id)
                context_data = build_client_context(
                    db=db,
                    client_id=cid,
                    user=current_user,
                    period=body.period,
                )
                client_context_text = build_context_prompt_fragment(context_data)
            except Exception:
                client_context_text = "Note: Client context unavailable."

        res = chatbot_service.chat(
            message=body.message.strip(),
            session_id=body.session_id,
            client_context=client_context_text,
        )
        return ChatResponse(**res)


@router.get(
    "/insights/{client_id}",
    response_model=AIInsightsResponse,
    summary="Get backend-grounded AI insights for a client",
)
def get_client_insights(
    client_id: uuid.UUID,
    period: Optional[str] = Query(None, description="Period e.g. '2026-07' or 'Q2 FY 2026-27'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns real, backend-derived AI insight cards for the given client.

    Every insight card is grounded in actual backend data (compliance score,
    discrepancies, unverified documents, filing checklist).

    SAFETY: Never returns hardcoded or fabricated insights.
    If no data is available, returns an empty list with a clear message.
    """
    from app.services.ai_context_service import build_client_context

    try:
        context = build_client_context(
            db=db,
            client_id=client_id,
            user=current_user,
            period=period,
            include_gst=True,
            include_discrepancies=True,
            include_insights=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    insights: List[AIInsightItem] = []
    idx = 1

    # ── Insight: Unverified documents ──────────────────────────────────────
    docs = context.get("documents") or {}
    unverified = docs.get("unverified", 0)
    if unverified > 0:
        insights.append(AIInsightItem(
            id=idx,
            text=f"{unverified} document{'s' if unverified > 1 else ''} remain unverified. "
                 "Please review and verify before filing.",
            severity="warning",
            source="backend",
        ))
        idx += 1

    pending_ocr = docs.get("pending_ocr", 0)
    if pending_ocr > 0:
        insights.append(AIInsightItem(
            id=idx,
            text=f"{pending_ocr} document{'s' if pending_ocr > 1 else ''} "
                 "pending OCR extraction.",
            severity="info",
            source="backend",
        ))
        idx += 1

    # ── Insight: Discrepancies ─────────────────────────────────────────────
    disc = context.get("discrepancies") or {}
    if disc.get("data_available", False):
        total_disc = disc.get("total_discrepancies", 0)
        if total_disc > 0:
            insights.append(AIInsightItem(
                id=idx,
                text=f"{total_disc} discrepanc{'ies' if total_disc > 1 else 'y'} detected "
                     "by the discrepancy engine — review before filing.",
                severity="danger",
                source="backend",
            ))
            idx += 1
            # Surface the first critical discrepancy specifically
            for item in (disc.get("items") or [])[:3]:
                desc = item.get("description", "")
                sev = item.get("severity", "warning")
                amt = item.get("amount")
                if desc:
                    amt_str = f" (₹{amt:,.2f})" if amt else ""
                    insights.append(AIInsightItem(
                        id=idx,
                        text=f"{desc}{amt_str}",
                        severity=sev if sev in ("danger", "warning", "info", "success") else "warning",
                        source="backend",
                    ))
                    idx += 1

    # ── Insight: Financial insights / compliance score ─────────────────────
    fi = context.get("financial_insights") or {}
    if fi.get("data_available", False):
        score = fi.get("compliance_score")
        if score is not None:
            if score < 50:
                sev = "danger"
            elif score < 75:
                sev = "warning"
            else:
                sev = "success"
            insights.append(AIInsightItem(
                id=idx,
                text=f"Compliance score: {score:.0f}/100.",
                severity=sev,
                source="backend",
            ))
            idx += 1

        pending_cl = fi.get("checklist_pending", 0)
        total_cl = fi.get("checklist_total", 0)
        if pending_cl > 0:
            insights.append(AIInsightItem(
                id=idx,
                text=f"{pending_cl} of {total_cl} filing checklist items are pending.",
                severity="warning",
                source="backend",
            ))
            idx += 1

        for obs in (fi.get("ca_observations") or [])[:3]:
            observation = obs.get("observation", "")
            rec = obs.get("recommendation", "")
            sev = obs.get("severity", "info")
            if observation:
                text = observation
                if rec:
                    text = f"{observation} → {rec}"
                insights.append(AIInsightItem(
                    id=idx,
                    text=text,
                    severity=sev if sev in ("danger", "warning", "info", "success") else "info",
                    source="backend",
                ))
                idx += 1

    # ── Insight: GST highlights ────────────────────────────────────────────
    gst = context.get("gst") or {}
    if gst.get("data_available", False):
        net = gst.get("net_tax_payable")
        if net is not None and net > 0:
            insights.append(AIInsightItem(
                id=idx,
                text=f"Net GST payable: ₹{net:,.2f} for the selected period.",
                severity="info",
                source="backend",
            ))
            idx += 1

    # ── Insight: Draft journal entries ──────────────────────────────────────
    journals = context.get("journals") or {}
    draft_count = journals.get("draft", 0)
    if draft_count > 0:
        insights.append(AIInsightItem(
            id=idx,
            text=f"{draft_count} journal entr{'ies' if draft_count > 1 else 'y'} remain in draft "
                 "status and have not been posted to the ledger.",
            severity="warning",
            source="backend",
        ))
        idx += 1

    client_info = context.get("client", {})

    if not insights:
        return AIInsightsResponse(
            client_id=str(client_id),
            client_name=client_info.get("name", "Unknown"),
            period=period,
            insights=[],
            data_available=False,
            message="No verified insights are available for this client yet.",
        )

    return AIInsightsResponse(
        client_id=str(client_id),
        client_name=client_info.get("name", "Unknown"),
        period=period,
        insights=insights,
        data_available=True,
        message=f"{len(insights)} insight{'s' if len(insights) > 1 else ''} generated from verified backend data.",
    )


@router.get(
    "/resolve-client",
    response_model=ClientResolveResponse,
    summary="Resolve a client name or GSTIN to a client_id",
)
def resolve_client(
    q: str = Query(..., description="Client name (partial) or GSTIN"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deterministic client resolution.

    - If `q` looks like a GSTIN (15 chars, starts with digit), resolve by GSTIN.
    - Otherwise resolve by name (partial match, case-insensitive).
    - Returns all matches for the authenticated user.
    - If multiple matches: ambiguous=True → caller must ask user to clarify.
    """
    from app.services.ai_context_service import (
        resolve_client_by_name,
        resolve_client_by_gstin,
    )

    q = q.strip()
    matches = []

    # GSTIN pattern: 15 characters starting with 2 digits
    import re
    if re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$", q.upper()):
        result = resolve_client_by_gstin(db, current_user, q)
        if result:
            matches = [result]
    else:
        matches = resolve_client_by_name(db, current_user, q)

    ambiguous = len(matches) > 1

    if not matches:
        return ClientResolveResponse(
            matches=[],
            ambiguous=False,
            message=f"No client found matching '{q}'. Please check the name or GSTIN.",
        )
    if ambiguous:
        return ClientResolveResponse(
            matches=[ClientMatch(**m) for m in matches],
            ambiguous=True,
            message=f"Multiple clients match '{q}'. Please specify which client you mean.",
        )

    return ClientResolveResponse(
        matches=[ClientMatch(**m) for m in matches],
        ambiguous=False,
        message=f"Client resolved: {matches[0]['name']}",
    )


@router.get("/session/new", response_model=SessionResponse, summary="Create a new chat session")
async def new_session(
    current_user: User = Depends(get_current_user),
):
    """Pre-create a session ID before sending the first message."""
    sid = chatbot_service.new_session()
    return SessionResponse(session_id=sid)


@router.delete(
    "/session/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear conversation history for a session",
)
async def clear_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete all conversation history for the given session."""
    chatbot_service.clear_session(session_id)


@router.get("/status", response_model=StatusResponse, summary="Check AI assistant status")
async def get_status(
    current_user: User = Depends(get_current_user),
):
    """Returns whether the Gemini API is configured and ready."""
    from app.core.config import get_settings
    settings = get_settings()
    ready = chatbot_service.is_ready
    return StatusResponse(
        ready=ready,
        model=settings.GEMINI_MODEL,
        message="Ready" if ready else "GEMINI_API_KEY not set — set it in backend/.env",
    )
