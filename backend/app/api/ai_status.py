import logging
import time
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import get_settings
from app.database import DbSession
from app.models.user import User
from app.services.user_ai import ai_service_for
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI"])

# The sidebar asks every minute from every open tab; one probe per window is plenty. Keyed by
# user, because each user can point the app at their own models.
CACHE_SECONDS = 20
_cache: dict[str, tuple[float, "AIStatusResponse"]] = {}


class AIStatusResponse(BaseModel):
    status: Literal["online", "model_missing", "offline", "disabled"]
    vision_model: str | None = None
    text_model: str | None = None
    missing_models: list[str] = []
    # Ollama only: models in memory right now (GET /api/ps). A configured model that is not
    # loaded is fine: Ollama loads it on the first request, which is just slower.
    url: str | None = None
    loaded_models: list[str] = []
    model_loaded: bool | None = None


def _matches(model: str, available: list[str]) -> bool:
    # Ollama lists "name:tag"; a configured name without a tag means ":latest".
    candidates = {model, model if ":" in model else f"{model}:latest"}
    return any(name in candidates for name in available)


def summarize(raw: dict) -> AIStatusResponse:
    endpoints = raw.get("endpoints", [])
    healthy = [ep for ep in endpoints if ep.get("status") == "healthy"]
    if not healthy:
        first = endpoints[0] if endpoints else {}
        return AIStatusResponse(
            status="offline",
            vision_model=first.get("vision_model"),
            text_model=first.get("text_model"),
        )
    endpoint = healthy[0]
    available = endpoint.get("available_models") or []
    wanted = [m for m in (endpoint.get("vision_model"), endpoint.get("text_model")) if m]
    missing = sorted({m for m in wanted if not _matches(m, available)})
    return AIStatusResponse(
        status="model_missing" if missing else "online",
        vision_model=endpoint.get("vision_model"),
        text_model=endpoint.get("text_model"),
        missing_models=missing,
        url=endpoint.get("url"),
    )


async def loaded_models(base_url: str) -> list[str] | None:
    """Models an Ollama server holds in memory, or None when the server is not Ollama (or
    does not answer /api/ps). Read only: asking never loads anything."""
    root = base_url.rstrip("/").removesuffix("/v1")
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{root}/api/ps")
        if response.status_code != 200:
            return None
        return [m.get("name") or m.get("model", "") for m in response.json().get("models", [])]
    except (httpx.HTTPError, ValueError) as e:
        logger.debug(f"Could not read loaded models from {root}: {e}")
        return None


async def with_loaded_models(result: AIStatusResponse) -> AIStatusResponse:
    if result.status != "online" or not result.url:
        return result
    loaded = await loaded_models(result.url)
    if loaded is None:
        return result
    wanted = [m for m in (result.vision_model, result.text_model) if m]
    result.loaded_models = loaded
    result.model_loaded = bool(wanted) and all(_matches(m, loaded) for m in wanted)
    return result


@router.get("/status", response_model=AIStatusResponse)
async def ai_status(
    db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> AIStatusResponse:
    if not get_settings().ai_enabled:
        return AIStatusResponse(status="disabled")
    key = str(current_user.id)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    ai = await ai_service_for(db, current_user.id)
    result = await with_loaded_models(summarize(await ai.check_health()))
    _cache[key] = (time.monotonic(), result)
    return result
