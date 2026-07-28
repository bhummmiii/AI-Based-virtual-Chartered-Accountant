# ============================================================
# Translation API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement translation endpoints
@router.get("/")
async def get_translation():
    return {"module": "translation", "status": "not implemented"}
