"""
Chatbot API Router
==================
POST   /api/v1/chatbot/chat                 — send a message, get AI reply
GET    /api/v1/chatbot/session/new          — create a new session ID
DELETE /api/v1/chatbot/session/{session_id} — clear conversation history
GET    /api/v1/chatbot/status               — check if Gemini is configured
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.chatbot_service import chatbot_service

router = APIRouter()


# ── Request / Response Schemas ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    session_id: Optional[str] = Field(None, description="Existing session ID for multi-turn chat")
    client_context: Optional[str] = Field(None, description="Optional client info for context")


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class SessionResponse(BaseModel):
    session_id: str


class StatusResponse(BaseModel):
    ready: bool
    model: str
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse, summary="Send a message to the AI CA assistant")
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Multi-turn chat with the AI Chartered Accountant.

    - Supply `session_id` from a previous response to continue a conversation.
    - Omit `session_id` to start a fresh conversation (a new one will be returned).
    - Optionally pass `client_context` (e.g. company name + GSTIN) so the AI
      can tailor its answers to the specific client.
    """
    if not body.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message cannot be empty",
        )

    result = chatbot_service.chat(
        message=body.message.strip(),
        session_id=body.session_id,
        client_context=body.client_context,
    )
    return ChatResponse(**result)


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
