from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    sales_pii_key: SecretStr = SecretStr("")
    sales_intelligence_v2_enabled: bool = False
    cors_origins: str = "http://localhost:3000"

    # Copilot telemetry: Settings reads .env; the SDK is configured explicitly.
    langsmith_tracing: bool = Field(
        default=False, validation_alias=AliasChoices("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "langsmith_tracing")
    )
    langsmith_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "langsmith_api_key"),
    )
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias=AliasChoices("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT", "langsmith_endpoint"),
    )
    langsmith_project: str = Field(
        default="", validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT", "langsmith_project")
    )
    # Development opt-in: redacted shared Q&A, node state and model messages.
    langsmith_capture_content: bool = False
    langsmith_sampling_rate: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_telemetry(self) -> "Settings":
        if self.app_env == "production" and self.langsmith_capture_content:
            raise ValueError("LangSmith content capture is only permitted in development")
        if not self.langsmith_project:
            self.langsmith_project = "p043-copilot-prod" if self.app_env == "production" else "p043-copilot-dev"
        return self

    # Roleplay telemetry uses its own account and project.
    roleplay_langsmith_tracing: bool = False
    roleplay_langsmith_api_key: SecretStr = SecretStr("")
    roleplay_langsmith_endpoint: str = "https://api.smith.langchain.com"
    roleplay_langsmith_project: str = ""
    roleplay_langsmith_capture_content: bool = False

    @model_validator(mode="after")
    def validate_roleplay_telemetry(self) -> "Settings":
        if self.app_env == "production" and self.roleplay_langsmith_capture_content:
            raise ValueError("Roleplay LangSmith content capture is only permitted in development")
        if not self.roleplay_langsmith_project:
            self.roleplay_langsmith_project = (
                "p043-roleplay-prod" if self.app_env == "production" else "p043-roleplay-dev"
            )
        return self

    # LLM Providers
    llm_provider: Literal["openai", "openrouter", "gemini", "grok", "deepseek"] = "openrouter"
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("openai_api_key", "OPENAI_API_KEY"),
    )
    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "openrouter_api_key",
            "OPENROUTER_API_KEY",
            "open_router_api_key",
            "OPEN_ROUTER_API_KEY",
            "open_router_api",
            "OPEN_ROUTER_API",
        ),
    )
    openrouter_model_name: str = Field(
        default="openai/gpt-6-luna",
        validation_alias=AliasChoices("openrouter_model_name", "OPENROUTER_MODEL_NAME"),
    )
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("gemini_api_key", "GEMINI_API_KEY", "google_api_key", "GOOGLE_API_KEY"),
    )
    grok_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("grok_api_key", "GROK_API_KEY", "xai_api_key", "XAI_API_KEY"),
    )
    deepseek_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("deepseek_api_key", "DEEPSEEK_API_KEY"),
    )

    practice_judge_provider: Literal["openai", "openrouter", "gemini", "grok", "deepseek"] = "openrouter"
    practice_judge_model: str = "deepseek/deepseek-v3.2"

    # Model Configuration
    model_name: str = Field(
        default="openai/gpt-6-luna",
        validation_alias=AliasChoices("model_name", "MODEL_NAME", "openrouter_model_name", "OPENROUTER_MODEL_NAME"),
    )
    embedding_model_name: str = "openai/text-embedding-3-small"
    embedding_provider: Literal["openai", "openrouter", "hash"] = "openrouter"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    retrieval_timeout_seconds: float = Field(default=20.0, gt=0)
    copilot_request_timeout_seconds: float = Field(default=180.0, gt=0)
    copilot_max_retrieval_rounds: int = Field(default=2, ge=1, le=2)
    copilot_max_queries_per_plan: int = Field(default=3, ge=1, le=8)
    copilot_max_search_calls: int = Field(default=5, ge=1, le=12)
    copilot_max_requirements: int = Field(default=18, ge=2, le=24)
    copilot_session_ttl_hours: int = Field(default=8, ge=1, le=168)
    copilot_max_llm_attempts: int = Field(default=8, ge=3, le=8)
    # Comma-separated task types enabled by the deployment administrator. Empty disables AI task creation.
    sales_ai_task_rules: str = ""
    copilot_final_reserve_seconds: float = Field(default=10.0, gt=0)
    # Profile caps include all queries in a round and every expanded evidence chunk.
    copilot_evidence_selection_strategy: Literal["rrf_context", "jev_context"] = "jev_context"
    copilot_jev_model: str = "typesafe/jev-1.14"
    copilot_jev_timeout_seconds: float = Field(default=12.0, gt=0, le=30)
    copilot_jev_concurrency: int = Field(default=4, ge=1, le=8)
    copilot_jev_relevance_min: float = Field(default=0.45, ge=0, le=1)
    copilot_jev_evidence_min: float = Field(default=0.55, ge=0, le=1)
    copilot_jev_contradiction_min: float = Field(default=0.70, ge=0, le=1)
    copilot_jev_injection_max: float = Field(default=0.70, ge=0, le=1)
    copilot_simple_dense_top_k: int = Field(default=8, ge=1, le=20)
    copilot_simple_bm25_top_k: int = Field(default=8, ge=1, le=20)
    copilot_simple_candidate_pool: int = Field(default=8, ge=1, le=40)
    copilot_simple_evidence_blocks: int = Field(default=4, ge=1, le=12)
    copilot_simple_context_characters: int = Field(default=6000, ge=2000, le=12000)
    copilot_simple_context_tokens: int = Field(default=4000, ge=1000, le=16000)
    copilot_complex_dense_top_k: int = Field(default=12, ge=1, le=20)
    copilot_complex_bm25_top_k: int = Field(default=12, ge=1, le=20)
    copilot_complex_candidate_pool: int = Field(default=18, ge=1, le=40)
    copilot_complex_evidence_blocks: int = Field(default=20, ge=1, le=40)
    copilot_complex_context_characters: int = Field(default=16000, ge=2000, le=32000)
    copilot_complex_context_tokens: int = Field(default=6500, ge=1000, le=16000)
    copilot_corrective_dense_top_k: int = Field(default=12, ge=1, le=20)
    copilot_corrective_bm25_top_k: int = Field(default=12, ge=1, le=20)
    copilot_corrective_candidate_pool: int = Field(default=24, ge=1, le=40)
    copilot_corrective_evidence_blocks: int = Field(default=28, ge=1, le=40)
    copilot_corrective_context_characters: int = Field(default=24000, ge=2000, le=32000)
    copilot_corrective_context_tokens: int = Field(default=9000, ge=1000, le=16000)
    copilot_analysis_timeout_seconds: float = Field(default=25, gt=0)
    copilot_plan_timeout_seconds: float = Field(default=15, gt=0)
    copilot_generate_timeout_seconds: float = Field(default=30, gt=0)
    copilot_check_timeout_seconds: float = Field(default=20, gt=0)
    copilot_analysis_max_tokens: int = Field(default=3600, ge=256)
    copilot_plan_max_tokens: int = Field(default=1600, ge=256)
    copilot_generate_max_tokens: int = Field(default=4000, ge=256)
    copilot_generate_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    copilot_check_max_tokens: int = Field(default=4400, ge=256)
    copilot_check_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    copilot_regenerate_min_seconds: float = Field(default=60, gt=0)
    copilot_corrective_min_seconds: float = Field(default=95, gt=0)
    copilot_max_concurrency: int = Field(default=4, ge=1, le=32)
    copilot_user_concurrency: int = Field(default=2, ge=1, le=8)
    copilot_rate_limit: int = Field(default=10, ge=1, le=120)
    copilot_exact_cache_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("copilot_exact_cache_enabled", "COPILOT_EXACT_CACHE_ENABLED"),
    )
    knowledge_manifest_dir: str = "./data/index_manifests"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Optional server-side voice providers. Prices are list-price estimates, not invoices.
    groq_api_key: str = ""
    google_tts_service_account_json: str = ""
    voice_stt_usd_per_hour: float = Field(default=0.04, ge=0)
    voice_tts_usd_per_million_characters: float = Field(default=16.0, ge=0)

    # Local authentication
    auth_cookie_name: str = Field(default="p043_session", min_length=1, max_length=100)
    auth_session_ttl_hours: int = Field(default=8, ge=1, le=168)
    auth_cookie_secure: bool = False
    bootstrap_manager_username: str = ""
    bootstrap_manager_display_name: str = ""
    bootstrap_manager_password: str = ""

    # Vector Store
    vector_store_type: Literal["chroma", "pgvector", "memory"] = "chroma"
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection_name: str = "vinfast_knowledge_openrouter_3_small"
    similarity_top_k: int = 4

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env != "production":
            return self
        if self.embedding_provider == "hash":
            raise ValueError("Hash embeddings are not allowed in production")
        if not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        if self.database_url.startswith("sqlite"):
            raise ValueError("Production requires a persistent external DATABASE_URL")
        if not self.database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL")
        if self.vector_store_type != "pgvector":
            raise ValueError("Production requires VECTOR_STORE_TYPE=pgvector")
        if (
            self.llm_provider == "openrouter" or self.embedding_provider == "openrouter"
        ) and not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required in production")
        if (self.llm_provider == "openai" or self.embedding_provider == "openai") and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
