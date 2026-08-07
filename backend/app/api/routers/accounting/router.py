# ============================================================
# Accounting API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement accounting endpoints
@router.get("/")
async def get_accounting():
    return {"module": "accounting", "status": "not implemented"}
