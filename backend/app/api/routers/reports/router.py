# ============================================================
# Reports API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement reports endpoints
@router.get("/")
async def get_reports():
    return {"module": "reports", "status": "not implemented"}
