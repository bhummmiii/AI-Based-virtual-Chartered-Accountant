# ============================================================
# Government API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement government endpoints
@router.get("/")
async def get_government():
    return {"module": "government", "status": "not implemented"}
