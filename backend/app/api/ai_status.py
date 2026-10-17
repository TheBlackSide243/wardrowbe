import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import get_settings
from app.database import DbSession
from app.models.user import User
from app.services.user_ai import ai_service_for
from app.utils.auth import get_current_user

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
    )


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
    result = summarize(await ai.check_health())
    _cache[key] = (time.monotonic(), result)
    return result
