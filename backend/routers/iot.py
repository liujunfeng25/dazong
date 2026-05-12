from fastapi import APIRouter, Depends

from dependencies import get_current_user

router = APIRouter(prefix="/iot", tags=["iot"])


@router.get("/home")
async def iot_home(_=Depends(get_current_user)):
    return {"message": "ok", "module": "iot"}
