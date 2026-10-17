"""The team deployment uses OpenRouter for both chat and semantic embeddings."""

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.services import llm


def test_defaults_use_openrouter_models_without_hash(monkeypatch):
    for variable in ("LLM_PROVIDER", "MODEL_NAME", "OPENROUTER_MODEL_NAME",
                     "EMBEDDING_PROVIDER", "EMBEDDING_MODEL_NAME", "CHROMA_COLLECTION_NAME"):
        monkeypatch.delenv(variable, raising=False)
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openrouter"
    assert settings.model_name == "openai/gpt-6-luna"
    assert settings.embedding_provider == "openrouter"
    assert settings.embedding_model_name == "openai/text-embedding-3-small"
    assert settings.chroma_collection_name == "vinfast_knowledge_openrouter_3_small"


def test_existing_openrouter_model_variable_is_supported(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL_NAME", "openai/gpt-6-luna")
    settings = Settings(_env_file=None)

    assert settings.model_name == "openai/gpt-6-luna"


def test_chat_and_embedding_clients_share_openrouter_endpoint(monkeypatch):
    settings = Settings(_env_file=None, OPENROUTER_API_KEY="test-key")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    chat = llm.get_llm()
    embeddings = llm.get_embeddings()

    assert chat.model_name == "openai/gpt-6-luna"
    assert str(chat.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"
    assert embeddings.model == "openai/text-embedding-3-small"
    assert str(embeddings.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"
    assert not isinstance(embeddings, llm.DeterministicHashEmbeddings)
    assert chat.extra_body is None
    checker = llm.get_llm(max_retries=0, max_tokens=1000, openrouter_reasoning_effort="none")
    assert checker.extra_body == {"reasoning": {"effort": "none"}}
    assert checker.max_tokens == 1000 and checker.max_retries == 0


def test_missing_openrouter_key_does_not_fall_back_to_hash(monkeypatch):
    settings = Settings(_env_file=None, OPENROUTER_API_KEY="")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        llm.get_embeddings()


def test_production_rejects_hash_even_if_explicitly_requested():
    with pytest.raises(ValidationError, match="Hash embeddings are not allowed"):
        Settings(_env_file=None, APP_ENV="production", EMBEDDING_PROVIDER="hash")


def test_copilot_preserves_choice_error_code_without_private_provider_message():
    from src.services.provider_response import CopilotChatOpenAI, ProviderResponseError

    model = CopilotChatOpenAI(api_key="test-key")
    with pytest.raises(ProviderResponseError) as caught:
        model._create_chat_result(
            {
                "choices": [
                    {
                        "finish_reason": "error",
                        "message": {"role": "assistant", "content": ""},
                        "error": {"code": 503, "message": "private prompt and secret"},
                    }
                ]
            }
        )
    assert caught.value.status_code == 503
    assert "private" not in str(caught.value)
