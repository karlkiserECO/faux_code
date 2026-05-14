"""Models + providers discovery API."""

from __future__ import annotations

from fastapi import APIRouter

from ..providers import list_providers
from ..providers.registry import list_models as registry_list_models

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/providers")
def get_providers():
    return [p.model_dump() for p in list_providers()]


@router.get("/models")
async def get_models():
    return await registry_list_models()
