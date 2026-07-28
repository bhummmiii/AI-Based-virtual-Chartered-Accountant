# ============================================================
# Chatbot API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement chatbot endpoints
@router.get("/")
async def get_chatbot():
    return {"module": "chatbot", "status": "not implemented"}
