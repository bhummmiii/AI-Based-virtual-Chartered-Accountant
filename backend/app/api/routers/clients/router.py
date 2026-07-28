# ============================================================
# Clients API Router
# ============================================================

from fastapi import APIRouter, Depends

router = APIRouter()


# TODO: Implement clients endpoints
@router.get("/")
async def get_clients():
    return {"module": "clients", "status": "not implemented"}
