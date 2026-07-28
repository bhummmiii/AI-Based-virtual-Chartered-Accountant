# ============================================================
# Ocr API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement ocr endpoints
@router.get("/")
async def get_ocr():
    return {"module": "ocr", "status": "not implemented"}
