"""Exact Match Response Cache for standalone Copilot sales queries."""

import hashlib
import logging
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from src.agents.copilot.state import CopilotResponse
from src.config import get_settings
from src.knowledge.validity import is_document_retrievable, parse_target_date, today_in_vietnam

logger = logging.getLogger(__name__)

# Context-dependent pronouns or personal expressions that must bypass cache
CONTEXT_DEPENDENT_PATTERNS = re.compile(
    r"\b(nó|xe này|xe đó|xe kia|bản này|bản đó|vừa nói|ở trên|trước đó|tôi|em|khách của em|hôm qua)\b",
    re.IGNORECASE,
)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Legacy helper preserved for backward compatibility."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def normalize_query_text(text: str) -> str:
    """Normalize query for exact cache matching.

    Normalizes Unicode to NFC and collapses whitespace.
    Preserves case and punctuation.
    """
    s = unicodedata.normalize("NFC", text or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_cache_key(
    query: str,
    domain: str = "all",
    lookup_date: str = "",
    date_mode: str = "current",
    corpus_fingerprint: str = "",
    chunking_identity: str = "",
    workflow_version: str = "v2",
    provider_model: str = "",
) -> str:
    """Build deterministic exact cache key."""
    norm_q = normalize_query_text(query)
    raw = (
        f"{norm_q}|{domain}|{lookup_date}|{date_mode}|"
        f"{corpus_fingerprint}|{chunking_identity}|{workflow_version}|{provider_model}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ExactCacheEnvelope(BaseModel):
    """Typed cache envelope with key, base CopilotResponse data and expiry."""

    cache_key: str
    response_data: dict[str, Any]
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at


SemanticCacheEntry = ExactCacheEnvelope


class ExactCacheService:
    """Exact Response Cache for verified standalone Copilot answers."""

    def __init__(
        self,
        ttl_hours: int = 24,
        max_entries: int = 500,
        similarity_threshold: float = 1.0,
    ):
        self.ttl = timedelta(hours=ttl_hours)
        self.max_entries = max_entries
        self.similarity_threshold = similarity_threshold
        self._keys: list[str] = []
        self._cache_map: dict[str, ExactCacheEnvelope] = {}
        self._last_fingerprint: str | None = None

    def invalidate_all(self) -> None:
        """Clear all cache entries."""
        self._cache_map.clear()
        self._keys.clear()
        self._last_fingerprint = None

    def evict(self, key: str) -> None:
        """Evict a single cache key."""
        self._cache_map.pop(key, None)
        if key in self._keys:
            self._keys.remove(key)

    def should_bypass(
        self,
        query: str,
        customer_context: str = "",
        session_id: str | None = None,
        history: list | None = None,
        memory_summary: str | None = None,
    ) -> bool:
        """Check if query must bypass cache (non-standalone, personalization or disabled)."""
        settings = get_settings()
        if not getattr(settings, "copilot_exact_cache_enabled", True):
            return True
        if session_id or history or memory_summary:
            return True
        if customer_context and len(customer_context.strip()) > 0:
            return True
        if CONTEXT_DEPENDENT_PATTERNS.search(query):
            return True
        return False

    async def get(
        self,
        query: str,
        domain: str = "all",
        target_date: date | str | None = None,
        resolved_date: str | None = None,
        customer_context: str = "",
        session_id: str | None = None,
        history: list | None = None,
        memory_summary: str | None = None,
        readiness_loader: Any = None,
    ) -> dict[str, Any] | None:
        """Look up verified answer by exact hash key."""
        if self.should_bypass(
            query,
            customer_context=customer_context,
            session_id=session_id,
            history=history,
            memory_summary=memory_summary,
        ):
            return None

        date_mode = "explicit" if target_date is not None else "current"
        lookup_date_str = str(target_date) if target_date else str(resolved_date or today_in_vietnam())

        from src.knowledge.chunking import CHUNK_OVERLAP, CHUNK_SIZE, chunking_identity
        from src.knowledge.index_readiness import load_snapshot

        try:
            snapshot = readiness_loader() if readiness_loader else load_snapshot()
        except Exception as exc:
            logger.debug("Readiness snapshot unavailable for cache get: %s", exc)
            return None

        # Check if corpus identity changed; invalidate stale readiness
        if self._last_fingerprint and self._last_fingerprint != snapshot.fingerprint:
            self.invalidate_all()
        self._last_fingerprint = snapshot.fingerprint

        settings = get_settings()
        chunk_id = chunking_identity(CHUNK_SIZE, CHUNK_OVERLAP)
        prov_model = f"{getattr(settings, 'copilot_llm_provider', 'openrouter')}:{settings.model_name}"

        key = build_cache_key(
            query=query,
            domain=domain,
            lookup_date=lookup_date_str,
            date_mode=date_mode,
            corpus_fingerprint=snapshot.fingerprint,
            chunking_identity=chunk_id,
            workflow_version="v2",
            provider_model=prov_model,
        )

        entry = self._cache_map.get(key)
        if not entry:
            return None

        if entry.is_expired():
            self.evict(key)
            return None

        # Validate cached response against schema
        try:
            resp = CopilotResponse.model_validate(entry.response_data)
        except Exception as val_err:
            logger.warning("Evicting invalid schema cache entry: %s", val_err)
            self.evict(key)
            return None

        # Validate citations against snapshot and validity
        target_d = parse_target_date(lookup_date_str) or today_in_vietnam()
        for cit in resp.citations:
            if cit.chunk_id not in snapshot.chunks:
                logger.info("Evicting cache entry: cited chunk %s missing from corpus", cit.chunk_id)
                self.evict(key)
                return None
            chunk = snapshot.chunks[cit.chunk_id]
            doc_meta = chunk.metadata
            if not is_document_retrievable(doc_meta, target_d):
                logger.info("Evicting cache entry: cited doc %s expired at %s", cit.document_id, target_d)
                self.evict(key)
                return None

        logger.info("Exact cache HIT for key %s (query: '%s')", key[:12], query[:60])
        return dict(entry.response_data)

    def put(
        self,
        query: str,
        response_data: dict[str, Any] | CopilotResponse,
        domain: str = "all",
        target_date: date | str | None = None,
        resolved_date: str | None = None,
        customer_context: str = "",
        session_id: str | None = None,
        history: list | None = None,
        memory_summary: str | None = None,
        readiness_loader: Any = None,
    ) -> None:
        """Save verified standalone answer into exact cache."""
        if self.should_bypass(
            query,
            customer_context=customer_context,
            session_id=session_id,
            history=history,
            memory_summary=memory_summary,
        ):
            return

        if isinstance(response_data, CopilotResponse):
            raw_dict = response_data.model_dump()
        else:
            raw_dict = dict(response_data)

        # Strictly cache only 'answered' status with non-empty citations
        if raw_dict.get("status") != "answered" or not raw_dict.get("citations"):
            return

        # Strip request_id, session_id, cached metadata to keep clean base response
        clean_dict = {
            "status": raw_dict["status"],
            "answer": raw_dict["answer"],
            "citations": raw_dict.get("citations", []),
            "product_insights": raw_dict.get("product_insights", []),
            "talking_points": [],
            "suggested_message": None,
            "suggested_next_question": None,
            "sales_actions": [],
            "missing_information": [],
            "clarification_question": None,
            "reason_code": None,
            "request_id": None,
        }

        try:
            CopilotResponse.model_validate(clean_dict)
        except Exception as val_err:
            logger.warning("Refusing to cache invalid CopilotResponse: %s", val_err)
            return

        date_mode = "explicit" if target_date is not None else "current"
        lookup_date_str = str(target_date) if target_date else str(resolved_date or today_in_vietnam())

        from src.knowledge.chunking import CHUNK_OVERLAP, CHUNK_SIZE, chunking_identity
        from src.knowledge.index_readiness import load_snapshot

        try:
            snapshot = readiness_loader() if readiness_loader else load_snapshot()
        except Exception as exc:
            logger.debug("Readiness snapshot unavailable for cache put: %s", exc)
            return

        settings = get_settings()
        chunk_id = chunking_identity(CHUNK_SIZE, CHUNK_OVERLAP)
        prov_model = f"{getattr(settings, 'copilot_llm_provider', 'openrouter')}:{settings.model_name}"

        key = build_cache_key(
            query=query,
            domain=domain,
            lookup_date=lookup_date_str,
            date_mode=date_mode,
            corpus_fingerprint=snapshot.fingerprint,
            chunking_identity=chunk_id,
            workflow_version="v2",
            provider_model=prov_model,
        )

        expires_at = datetime.now(UTC) + self.ttl
        envelope = ExactCacheEnvelope(cache_key=key, response_data=clean_dict, expires_at=expires_at)

        if key in self._cache_map:
            self._cache_map[key] = envelope
            return

        if len(self._keys) >= self.max_entries:
            oldest_key = self._keys.pop(0)
            self._cache_map.pop(oldest_key, None)

        self._keys.append(key)
        self._cache_map[key] = envelope


SemanticCacheService = ExactCacheService
semantic_cache = ExactCacheService()
