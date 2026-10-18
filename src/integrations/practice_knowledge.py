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

# Charging tariffs and charging offers live in charging policies, not the car price list or sales promotions.
# A bare "kWh" is battery capacity ("pin 37,23 kWh"), a spec claim; only a per-kWh price is a tariff.
_CHARGING_CLAIM = re.compile(
    r"(?:VNĐ|đồng|đ)\s*(?:/|(?:cho\s+)?(?:mỗi|một|1)\s+)\s*kWh|(?:trạm|trụ|phiên|giá|phí|tiền|ưu đãi)\s+sạc|sạc\s+miễn\s+phí",
    re.I,
)


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
        general_top_k: int = 3,
        max_claims: int = 16,
    ) -> None:
        if top_k_per_claim < 1:
            raise ValueError("top_k_per_claim must be positive")
        if general_top_k < 0:
            raise ValueError("general_top_k must not be negative")
        if max_claims < 1:
            raise ValueError("max_claims must be positive")
        self._retrieval_service = retrieval_service
        self._top_k_per_claim = top_k_per_claim
        self._general_top_k = general_top_k
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
            charging = not warranty and bool(_CHARGING_CLAIM.search(claim.text))
            promotion = not charging and (
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
            elif charging:
                document_type = DocumentType.POLICY.value
                top_k = 24
            elif promotion:
                document_type = DocumentType.PROMOTION.value
                top_k = 24
            elif product_model and claim.category == "price":
                document_type = DocumentType.PRICE_LIST.value
                top_k = 24  # The MSRP table is one small chunk in a long official PDF.
            elif product_model and (
                claim.category == "product"
                or (
                    claim.category == "battery_charging"
                    and re.search(r"(?<![^\W\d])km\b|kWh|quãng đường|đi được", claim.text, re.I)
                )
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
            elif charging:
                candidates = [chunk for chunk in candidates if chunk.metadata.policy_type == "charging"]
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
            fell_back = (warranty or charging or promotion) and not candidates
            if fell_back:
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
                    promotion and not _names_same_program(claim.text, chunk),
                    chunk.document_id.startswith("PRODUCT_"),
                    not bool(trim and re.search(rf"\b{trim.group(1)}\b", chunk.content, re.I)),
                )
            )
            chunks = candidates[: self._top_k_per_claim]
            # Keep MSRP evidence independently of the promotion candidate budget.
            chunks.extend(price_evidence[: self._top_k_per_claim])
            # The routed source is a preference, not a filter: a claim routed to the
            # wrong source still reaches the judge with its best unrouted matches.
            # A preferred-source miss has already fallen back to the same general search.
            routed = document_type is not None or warranty or charging or promotion
            if self._general_top_k and routed and not fell_back:
                general = self._retrieval_service.retrieve(
                    claim.text,
                    top_k=self._general_top_k,
                    product_model=product_model,
                    document_type=None,
                    target_date=state.target_date,
                )
                chunks.extend(chunk for chunk in general if valid_policy_chunk(chunk, state.target_date))
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


def _names_same_program(claim_text: str, chunk: KnowledgeChunk) -> bool:
    """Whether the chunk's section heading shares a three-word run with the claim, e.g. a program name."""
    heading = next((line for line in chunk.content.splitlines() if line.strip()), "")
    claim_words, heading_words = re.findall(r"\w+", claim_text.lower()), re.findall(r"\w+", heading.lower())
    claim_runs = {tuple(claim_words[i : i + 3]) for i in range(len(claim_words) - 2)}
    return any(tuple(heading_words[i : i + 3]) in claim_runs for i in range(len(heading_words) - 2))
