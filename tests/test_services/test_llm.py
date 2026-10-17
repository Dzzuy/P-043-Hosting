import pytest

from src.config import Settings
from src.services import llm as llm_service


def test_openrouter_uses_provider_specific_model(monkeypatch):
    settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key="sk-or-v1-test-only",
        openrouter_model_name="openai/gpt-6-luna",
    )
    monkeypatch.setattr(llm_service, "get_settings", lambda: settings)

    model = llm_service.get_llm()

    assert model.model_name == "openai/gpt-6-luna"
    assert str(model.openai_api_base) == "https://openrouter.ai/api/v1"
    assert model.extra_body is None


def test_openrouter_fails_before_network_call_when_key_is_missing(monkeypatch):
    settings = Settings(llm_provider="openrouter", openrouter_api_key="")
    monkeypatch.setattr(llm_service, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="openrouter is not configured"):
        llm_service.get_llm()


def test_openrouter_accepts_separate_practice_judge_model(monkeypatch):
    settings = Settings(openrouter_api_key="test-only")
    monkeypatch.setattr(llm_service, "get_settings", lambda: settings)
    model = llm_service.get_llm(
        provider=settings.practice_judge_provider, model=settings.practice_judge_model, temperature=0
    )
    assert model.model_name == "google/gemini-3.8-flash"
    assert model.temperature == 0
