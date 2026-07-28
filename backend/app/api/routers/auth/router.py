# ============================================================
# Auth API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement auth endpoints
@router.get("/")
async def get_auth():
    return {"module": "auth", "status": "not implemented"}
