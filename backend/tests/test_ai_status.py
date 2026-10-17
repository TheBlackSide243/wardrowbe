from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image

from app.api import ai_status


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (400, 600), (90, 90, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


class TestAIStatus:
    def test_summarize_reports_a_missing_model(self):
        raw = {
            "endpoints": [
                {
                    "status": "healthy",
                    "vision_model": "Ornith-1.5-9B",
                    "text_model": "hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q5_K_M",
                    "available_models": ["hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q5_K_M"],
                }
            ]
        }
        result = ai_status.summarize(raw)
        assert result.status == "model_missing"
        assert result.missing_models == ["Ornith-1.5-9B"]

    def test_summarize_online_and_offline(self):
        online = {
            "endpoints": [
                {
                    "status": "healthy",
                    "vision_model": "gemma3",
                    "text_model": "gemma3",
                    "available_models": ["gemma3:latest"],
                }
            ]
        }
        assert ai_status.summarize(online).status == "online"
        offline = {"endpoints": [{"status": "unhealthy", "vision_model": "gemma3"}]}
        assert ai_status.summarize(offline).status == "offline"

    @pytest.mark.asyncio
    async def test_endpoint_needs_sign_in_and_answers(self, client: AsyncClient, auth_headers):
        assert (await client.get("/api/v1/ai/status")).status_code == 401
        ai_status._cache.clear()
        health = {
            "status": "unhealthy",
            "endpoints": [{"status": "unhealthy", "vision_model": "m", "text_model": "m"}],
        }
        with patch(
            "app.services.ai_service.AIService.check_health", AsyncMock(return_value=health)
        ):
            response = await client.get("/api/v1/ai/status", headers=auth_headers)
        ai_status._cache.clear()
        assert response.status_code == 200
        assert response.json()["status"] in ("offline", "disabled")


class TestUserModels:
    @pytest.mark.asyncio
    async def test_the_users_own_endpoint_comes_first(self, db_session, test_user):
        from app.models.preference import UserPreference
        from app.services.user_ai import ai_service_for

        db_session.add(
            UserPreference(
                user_id=test_user.id,
                ai_endpoints=[
                    {
                        "name": "mine",
                        "url": "http://ollama.local:11434/v1",
                        "vision_model": "qwen2.5vl:7b",
                        "text_model": "qwen3:8b",
                        "enabled": True,
                    },
                    {"name": "off", "url": "http://off/v1", "enabled": False},
                ],
            )
        )
        await db_session.commit()

        ai = await ai_service_for(db_session, test_user.id)
        first = ai._endpoints[0]
        assert (first.url, first.vision_model, first.text_model) == (
            "http://ollama.local:11434/v1",
            "qwen2.5vl:7b",
            "qwen3:8b",
        )
        assert all(ep.name != "off" for ep in ai._endpoints)

    @pytest.mark.asyncio
    async def test_without_own_endpoints_the_server_default_is_used(self, db_session, test_user):
        from app.services.ai_service import get_ai_service
        from app.services.user_ai import ai_service_for

        assert await ai_service_for(db_session, test_user.id) is get_ai_service()
