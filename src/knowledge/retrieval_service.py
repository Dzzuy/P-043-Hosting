"""Vector retrieval and corpus ingestion used by the baseline and shared callers."""

from datetime import date
from typing import Any

from src.knowledge.embedding import KnowledgeEmbeddingService
from src.knowledge.schemas import DocumentType, KnowledgeChunk
from src.knowledge.validity import is_document_retrievable
from src.knowledge.vector_store import BaseVectorStore, get_vector_store
from src.observability import span


class RetrievalService:
    def __init__(
        self,
        vector_store: BaseVectorStore | None = None,
        embedding_service: KnowledgeEmbeddingService | None = None,
    ):
        self.vector_store = vector_store if vector_store is not None else get_vector_store()
        self.embedding_service = embedding_service if embedding_service is not None else KnowledgeEmbeddingService()

    def ingest_corpus(self, corpus_path: str = "data/knowledge/corpus.json", reset: bool = False) -> int:
        from src.agents.copilot.tools import get_bm25_search_engine
        from src.knowledge.ingestion import KnowledgeIngestionPipeline

        pipeline = KnowledgeIngestionPipeline(self.vector_store, self.embedding_service)
        report = pipeline.run(corpus_path, reset=reset)
        get_bm25_search_engine().reindex(corpus_path)
        return report["chunks"]

    def retrieve_with_scores(
        self,
        query: str,
        product_model: str | None = None,
        document_type: str | None = None,
        policy_type: str | None = None,
        top_k: int = 4,
        target_date: date | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        if top_k <= 0 or not query.strip() or self.vector_store.count() == 0:
            return []
        where: dict[str, Any] = {}
        if product_model and product_model.upper() != "ALL":
            where["product_model"] = (
                product_model if document_type == DocumentType.PRODUCT_SPECS.value else [product_model, "ALL"]
            )
        if document_type:
            where["document_type"] = document_type
        if policy_type:
            where["policy_type"] = policy_type
        query_vector = self.embedding_service.embed_query(query)
        # Grow the candidate window if date filtering consumed the closest hits.
        total = self.vector_store.count()
        fetch_k = min(total, max(top_k * 2, top_k + 2))
        iterations = 0
        while True:
            iterations += 1
            with span("retrieval.candidates", fetch_k=fetch_k, top_k=top_k, iterations=iterations) as metadata:
                candidates = self.vector_store.similarity_search_with_scores(query_vector, fetch_k, where or None)
                valid = [
                    (chunk, score)
                    for chunk, score in candidates
                    if is_document_retrievable(chunk.metadata, target_date)
                ]
                metadata.update(candidate_count=len(candidates), result_count=min(len(valid), top_k))
            if len(valid) >= top_k or fetch_k >= total or len(candidates) < fetch_k:
                return valid[:top_k]
            fetch_k = min(total, fetch_k * 2)

    def retrieve(
        self,
        query: str,
        product_model: str | None = None,
        document_type: str | None = None,
        policy_type: str | None = None,
        top_k: int = 4,
        target_date: date | None = None,
    ) -> list[KnowledgeChunk]:
        return [
            chunk
            for chunk, _ in self.retrieve_with_scores(
                query=query,
                product_model=product_model,
                document_type=document_type,
                policy_type=policy_type,
                top_k=top_k,
                target_date=target_date,
            )
        ]


_retrieval_service_instance: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service_instance
    if _retrieval_service_instance is None:
        _retrieval_service_instance = RetrievalService()
    return _retrieval_service_instance
