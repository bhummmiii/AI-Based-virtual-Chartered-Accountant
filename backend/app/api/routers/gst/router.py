# ============================================================
# Gst API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement gst endpoints
@router.get("/")
async def get_gst():
    return {"module": "gst", "status": "not implemented"}
