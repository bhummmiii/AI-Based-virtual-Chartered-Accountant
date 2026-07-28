# ============================================================
# Audit API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement audit endpoints
@router.get("/")
async def get_audit():
    return {"module": "audit", "status": "not implemented"}
