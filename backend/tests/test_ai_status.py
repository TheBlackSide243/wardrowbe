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


class TestOllamaSettings:
    def test_ollama_variables_fill_in_the_ai_settings(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434/")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5vl:7b")
        monkeypatch.setenv("OLLAMA_TEXT_MODEL", "qwen3:8b")
        monkeypatch.setenv("OLLAMA_TIMEOUT", "240")
        settings = Settings()
        assert settings.ai_base_url == "http://ollama:11434/v1"
        assert settings.ai_vision_model == "qwen2.5vl:7b"
        assert settings.ai_text_model == "qwen3:8b"
        assert settings.ai_timeout == 240

    def test_a_v1_url_is_kept_and_ai_settings_stay_without_ollama_ones(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.5:11434/v1")
        assert Settings().ai_base_url == "http://192.168.1.5:11434/v1"
        monkeypatch.delenv("OLLAMA_BASE_URL")
        monkeypatch.setenv("AI_BASE_URL", "http://other:8080/v1")
        monkeypatch.setenv("AI_VISION_MODEL", "llava")
        settings = Settings()
        assert (settings.ai_base_url, settings.ai_vision_model) == ("http://other:8080/v1", "llava")


class TestLoadedModels:
    def _online(self):
        return ai_status.AIStatusResponse(
            status="online",
            vision_model="qwen2.5vl:7b",
            text_model="qwen2.5vl:7b",
            url="http://ollama:11434/v1",
        )

    @pytest.mark.asyncio
    async def test_reports_whether_the_model_is_in_memory(self):
        with patch("app.api.ai_status.loaded_models", AsyncMock(return_value=["qwen2.5vl:7b"])):
            assert (await ai_status.with_loaded_models(self._online())).model_loaded is True
        with patch("app.api.ai_status.loaded_models", AsyncMock(return_value=[])):
            result = await ai_status.with_loaded_models(self._online())
        # Reachable with the model installed but not loaded: still online, loads on first use.
        assert result.status == "online"
        assert result.model_loaded is False

    @pytest.mark.asyncio
    async def test_a_server_without_api_ps_leaves_it_unknown(self):
        with patch("app.api.ai_status.loaded_models", AsyncMock(return_value=None)):
            assert (await ai_status.with_loaded_models(self._online())).model_loaded is None

    @pytest.mark.asyncio
    async def test_an_unreachable_server_is_unknown_not_an_error(self):
        assert await ai_status.loaded_models("http://127.0.0.1:9/v1") is None


class TestBackgroundModelUnload:
    def test_the_session_is_dropped_after_idle_time(self):
        import time
        from unittest.mock import MagicMock

        from app.services.background_removal import RembgProvider

        provider = RembgProvider(model="u2net", idle_seconds=0.05)
        fake = MagicMock(new_session=MagicMock(return_value="session"), remove=MagicMock())
        with patch.dict("sys.modules", {"rembg": fake}):
            provider.remove(Image.new("RGB", (4, 4)))
            assert provider._session == "session"
            time.sleep(0.3)
        assert provider._session is None
