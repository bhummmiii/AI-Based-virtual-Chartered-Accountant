# ============================================================
# Tax API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement tax endpoints
@router.get("/")
async def get_tax():
    return {"module": "tax", "status": "not implemented"}
