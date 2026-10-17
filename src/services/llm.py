import hashlib
import math

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src.config import get_settings


class DeterministicHashEmbeddings(Embeddings):
    """Deterministic local embeddings generator for testing and offline development.

    Generates normalized 1536-dimensional vectors using SHA-256 tokens,
    providing repeatable lexical vectors without external API calls.
    This is not a semantic embedding model and must be selected explicitly.
    """

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def _embed_text(self, text: str) -> list[float]:
        tokens = text.lower().split()
        vector = [0.0] * self.dimension
        if not tokens:
            return vector

        for token in tokens:
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            for i in range(min(16, self.dimension)):
                idx = (h + i * 37) % self.dimension
                val = ((h >> (i * 4)) & 0xFF) / 255.0 - 0.5
                vector[idx] += val

        # Normalize L2
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_text(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_retries: int = 2,
    max_tokens: int | None = None,
    openrouter_reasoning_effort: str | None = None,
    copilot_provider_errors: bool = False,
) -> BaseChatModel:
    """Factory creating LLM clients for multi-provider environments.

    Supports:
    - openai: Standard OpenAI API
    - openrouter: OpenRouter unified gateway (base_url: https://openrouter.ai/api/v1)
    - gemini: Google Gemini via OpenAI-compatible endpoint
    - grok: xAI Grok (base_url: https://api.x.ai/v1)
    - deepseek: DeepSeek (base_url: https://api.deepseek.com/v1)
    """
    settings = get_settings()
    prov = (provider or settings.llm_provider).lower()
    temp = settings.llm_temperature if temperature is None else temperature

    # Auto-detect OpenRouter if default is OpenAI but user configured OpenRouter
    if provider is None and prov == "openai" and not settings.openai_api_key and settings.openrouter_api_key:
        prov = "openrouter"

    provider_keys = {
        "openai": settings.openai_api_key,
        "openrouter": settings.openrouter_api_key,
        "gemini": settings.gemini_api_key,
        "grok": settings.grok_api_key,
        "deepseek": settings.deepseek_api_key,
    }
    if prov not in provider_keys or not provider_keys[prov]:
        raise ValueError(f"API key for LLM provider {prov} is not configured")

    if prov == "openrouter":
        from src.services.provider_response import CopilotChatOpenAI

        api_key = settings.openrouter_api_key
        target_model = model or settings.model_name
        if "/" not in target_model:
            if "gemini" in target_model.lower():
                model_name = f"google/{target_model}"
            else:
                model_name = f"openai/{target_model}"
        else:
            model_name = target_model
        return (CopilotChatOpenAI if copilot_provider_errors else ChatOpenAI)(
            model=model_name,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            extra_body={"reasoning": {"effort": openrouter_reasoning_effort}} if openrouter_reasoning_effort else None,
            temperature=temp,
            timeout=settings.llm_timeout_seconds,
            max_retries=max_retries,
            max_tokens=max_tokens,
        )

    if prov == "gemini":
        api_key = settings.gemini_api_key
        model_name = model or "gemini-1.5-flash"
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            temperature=temp,
            timeout=settings.llm_timeout_seconds,
            max_retries=max_retries,
            max_tokens=max_tokens,
        )

    if prov == "grok":
        api_key = settings.grok_api_key
        model_name = model or "grok-beta"
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            temperature=temp,
            timeout=settings.llm_timeout_seconds,
            max_retries=max_retries,
            max_tokens=max_tokens,
        )

    if prov == "deepseek":
        api_key = settings.deepseek_api_key
        model_name = model or "deepseek-chat"
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            temperature=temp,
            timeout=settings.llm_timeout_seconds,
            max_retries=max_retries,
            max_tokens=max_tokens,
        )

    # Default: openai
    api_key = settings.openai_api_key
    model_name = model or settings.model_name
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        temperature=temp,
        timeout=settings.llm_timeout_seconds,
        max_retries=max_retries,
        max_tokens=max_tokens,
    )


def get_embeddings() -> Embeddings:
    """Use the configured embedder; never substitute hash vectors for semantic vectors."""
    settings = get_settings()
    if settings.embedding_provider == "hash":
        return DeterministicHashEmbeddings(dimension=1536)
    if settings.embedding_provider == "openrouter":
        if not settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required for the configured OpenRouter embedder")
        model = settings.embedding_model_name
        return OpenAIEmbeddings(
            model=model if "/" in model else f"openai/{model}",
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            check_embedding_ctx_length=False,
            request_timeout=settings.retrieval_timeout_seconds,
            max_retries=2,
        )
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for the configured OpenAI embedder")
    return OpenAIEmbeddings(
        model=settings.embedding_model_name,
        api_key=settings.openai_api_key,
        request_timeout=settings.retrieval_timeout_seconds,
        max_retries=0,
    )
