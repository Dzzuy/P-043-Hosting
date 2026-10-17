"""Ground role-play factual claims with the shared knowledge retrieval service."""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Protocol

from src.agents.roleplay.contracts import ScenarioContract
from src.agents.roleplay.evaluator import KnowledgeEvidence
from src.agents.roleplay.state import RoleplayState
from src.knowledge.schemas import DocumentType, KnowledgeChunk

from .practice_policy import valid_policy_chunk

logger = logging.getLogger(__name__)


class KnowledgeRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 4,
        product_model: str | None = None,
        document_type: str | None = None,
        target_date: date | None = None,
    ) -> list[KnowledgeChunk]: ...


class RetrievalKnowledgeEvidenceProvider:
    """Retrieve bounded, deduplicated evidence for exact advisor claims."""

    def __init__(
        self,
        retrieval_service: KnowledgeRetriever,
        *,
        top_k_per_claim: int = 3,
        max_claims: int = 16,
    ) -> None:
        if top_k_per_claim < 1:
            raise ValueError("top_k_per_claim must be positive")
        if max_claims < 1:
            raise ValueError("max_claims must be positive")
        self._retrieval_service = retrieval_service
        self._top_k_per_claim = top_k_per_claim
        self._max_claims = max_claims

    async def for_session(
        self,
        scenario: ScenarioContract,
        state: RoleplayState,
    ) -> list[KnowledgeEvidence]:
        if scenario.scenario_id != state.scenario_id:
            raise ValueError("state and scenario identifiers do not match")

        unique_claims = list({claim.text: claim for claim in state.factual_claims}.values())
        if len(unique_claims) > self._max_claims:
            logger.warning("Knowledge evidence claim cap dropped %d claims", len(unique_claims) - self._max_claims)
        unique_claims = unique_claims[: self._max_claims]
        chunks_by_id: dict[str, KnowledgeChunk] = {}
        for claim in unique_claims:
            model_match = re.search(
                r"\bVF\s*[3-9]\b", f"{claim.text} {scenario.title} {scenario.visible_context}", re.I
            )
            product_model = f"VF {model_match.group(0)[-1]}" if model_match else None
            document_type = None
            top_k = self._top_k_per_claim
            warranty = bool(re.search("bảo hành", claim.text, re.I)) or claim.category == "warranty"
            promotion = (
                bool(
                    re.search(
                        r"ưu đãi|giảm giá|giảm\s+\d+(?:[.,]\d+)?\s*%|Vì Tương Lai Xanh|khuyến mãi|chiết khấu",
                        claim.text,
                        re.I,
                    )
                )
                or claim.category == "promotion"
            )
            if warranty:
                top_k = 24
            elif promotion:
                document_type = DocumentType.PROMOTION.value
                top_k = 24
            elif product_model and claim.category == "price":
                document_type = DocumentType.PRICE_LIST.value
                top_k = 24  # The MSRP table is one small chunk in a long official PDF.
            elif product_model and (
                claim.category == "product"
                or (claim.category == "battery_charging" and re.search(r"\bkm\b|quãng đường|đi được", claim.text, re.I))
            ):
                document_type = DocumentType.PRODUCT_SPECS.value

            trim = re.search(r"\b(Eco|Plus)\b", claim.text, re.I) if product_model in {"VF 6", "VF 7"} else None
            if trim:
                top_k = max(top_k, 24)
            candidates = self._retrieval_service.retrieve(
                claim.text,
                top_k=top_k,
                product_model=product_model,
                document_type=document_type,
                target_date=state.target_date,
            )
            if document_type == DocumentType.PRICE_LIST.value:
                candidates = [
                    chunk
                    for chunk in candidates
                    if product_model in chunk.content and "Giá bán bán lẻ đề xuất" in chunk.content
                ]
            price_evidence: list[KnowledgeChunk] = []
            if warranty:
                model_id = product_model.replace(" ", "") if product_model else ""
                candidates = [chunk for chunk in candidates if chunk.document_id.startswith(f"FAQ_{model_id}")]
            elif promotion:
                candidates = [chunk for chunk in candidates if chunk.document_id.startswith("PROMOTION_SALES_VINFAST_")]
                # Discount calculations need both the promotion and the MSRP table.
                if product_model and (claim.category == "price" or re.search(r"triệu|giá|đồng", claim.text, re.I)):
                    prices = self._retrieval_service.retrieve(
                        claim.text,
                        top_k=24,
                        product_model=product_model,
                        document_type=DocumentType.PRICE_LIST.value,
                        target_date=state.target_date,
                    )
                    price_evidence = list(
                        chunk
                        for chunk in prices
                        if product_model in chunk.content and "Giá bán bán lẻ đề xuất" in chunk.content
                    )
            # Preferred-source misses must not erase otherwise useful evidence.
            # FAQ IDs are not a document_type, so warranty preference is applied
            # to the model-scoped candidates above; fallback retains all sources.
            if (warranty or promotion) and not candidates:
                candidates = self._retrieval_service.retrieve(
                    claim.text,
                    top_k=self._top_k_per_claim,
                    product_model=product_model,
                    document_type=None,
                    target_date=state.target_date,
                )
            candidates = [chunk for chunk in candidates if valid_policy_chunk(chunk, state.target_date)]
            price_evidence = [chunk for chunk in price_evidence if valid_policy_chunk(chunk, state.target_date)]
            candidates.sort(
                key=lambda chunk: (
                    chunk.document_id.startswith("PRODUCT_"),
                    not bool(trim and re.search(rf"\b{trim.group(1)}\b", chunk.content, re.I)),
                )
            )
            chunks = candidates[: self._top_k_per_claim]
            # Keep MSRP evidence independently of the promotion candidate budget.
            chunks.extend(price_evidence[: self._top_k_per_claim])
            for chunk in chunks:
                chunks_by_id.setdefault(chunk.chunk_id, chunk)

        return [
            KnowledgeEvidence(
                source_id=chunk.chunk_id,
                version=chunk.metadata.version,
                content=chunk.content,
            )
            for chunk in chunks_by_id.values()
        ]
