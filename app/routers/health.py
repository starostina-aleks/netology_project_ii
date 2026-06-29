import asyncio

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/health", tags=["health"])

@router.get(
    ""
)

async def print_health() ->dict[str, str]:
    return {"status":"ok"}
