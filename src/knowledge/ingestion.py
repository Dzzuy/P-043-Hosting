"""Validate and embed the complete corpus before any destructive index reset."""

import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path when executed directly as a script
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.knowledge.chunking import CHUNK_OVERLAP, CHUNK_SIZE, CHUNKING_STRATEGY, chunking_identity  # noqa: E402
from src.knowledge.embedding import KnowledgeEmbeddingService  # noqa: E402
from src.knowledge.index_readiness import load_snapshot, manifest_path, write_manifest  # noqa: E402
from src.knowledge.vector_store import BaseVectorStore, get_vector_store  # noqa: E402

logger = logging.getLogger(__name__)


class KnowledgeIngestionPipeline:
    def __init__(
        self,
        vector_store: BaseVectorStore | None = None,
        embedding_service: KnowledgeEmbeddingService | None = None,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ):
        self.vector_store = vector_store if vector_store is not None else get_vector_store()
        self.embedding_service = embedding_service if embedding_service is not None else KnowledgeEmbeddingService()
        self.chunk_size, self.chunk_overlap = chunk_size, chunk_overlap

    def run(self, corpus_path: str | Path = "data/knowledge/corpus.json", reset: bool = False) -> dict[str, Any]:
        start = time.perf_counter()
        snapshot = load_snapshot(corpus_path, self.chunk_size, self.chunk_overlap)
        documents = list(snapshot.documents)
        if len({doc.document_id for doc in documents}) != len(documents):
            raise ValueError("Corpus contains duplicate document IDs")
        chunks = list(snapshot.chunks.values())
        if not chunks or any(not doc.content.strip() for doc in documents):
            raise ValueError("Corpus contains empty document content")
        settings = get_settings()
        # Do not overwrite an old index before discovering its chunking is incompatible.
        if self.vector_store.count() and not reset:
            path = manifest_path(settings)
            manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            if manifest.get("format") != 2 or manifest.get("chunking") != chunking_identity(
                self.chunk_size, self.chunk_overlap
            ):
                raise ValueError("Chunking changed or provenance missing; ingest into a new collection")
        vectors = self.embedding_service.embed_chunks(chunks)
        if len(vectors) != len(chunks) or not vectors or not vectors[0]:
            raise ValueError("Embedding output does not match the corpus chunks")
        if any(len(vector) != len(vectors[0]) for vector in vectors):
            raise ValueError("Embedding output contains inconsistent vector dimensions")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise ValueError("Embedding output contains non-finite values")
        from src.knowledge.index_readiness import embedding_identity

        if self.embedding_service.provenance != embedding_identity(settings):
            raise ValueError("Embedding service does not match configured provenance")
        if reset:
            self.vector_store.reset()
        try:
            self.vector_store.upsert_chunks(chunks, vectors)
        except Exception as exc:
            logger.error("Failed to upsert chunks into vector store: %s", exc)
            raise RuntimeError(f"Failed to upsert chunks into vector store: {exc}") from exc
        write_manifest(
            self.vector_store, snapshot, settings, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap
        )
        return {
            "status": "success",
            "documents": len(documents),
            "chunks": len(chunks),
            "chunking_strategy": CHUNKING_STRATEGY,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "chunk_unit": "characters",
            "recursive_fallback_chunks": sum(chunk.metadata.requires_context for chunk in chunks),
            "embedding_model": self.embedding_service.model_name,
            "vector_store": self.vector_store.__class__.__name__,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "errors": [],
        }


if __name__ == "__main__":
    import argparse

    from src.agents.copilot.tools import get_bm25_search_engine
    from src.knowledge.retrieval_service import get_retrieval_service

    parser = argparse.ArgumentParser(description="Ingest corpus without resetting existing data by default")
    parser.add_argument("--corpus", default="data/knowledge/corpus.json")
    parser.add_argument("--reset", action="store_true", help="Explicitly replace all existing vectors")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and preview chunks without embedding or storage writes"
    )
    args = parser.parse_args()

    if args.dry_run:
        snapshot = load_snapshot(args.corpus)
        lengths = [len(chunk.content) for chunk in snapshot.chunks.values()]
        print(
            json.dumps(
                {
                    "status": "preview",
                    "documents": len(snapshot.documents),
                    "chunks": len(lengths),
                    "chunking": chunking_identity(),
                    "min_chunk_characters": min(lengths),
                    "max_chunk_characters": max(lengths),
                    "recursive_fallback_chunks": sum(c.metadata.requires_context for c in snapshot.chunks.values()),
                    "chunks_by_document": {
                        doc.document_id: sum(c.document_id == doc.document_id for c in snapshot.chunks.values())
                        for doc in snapshot.documents
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(0)

    retriever = get_retrieval_service()
    pipeline = KnowledgeIngestionPipeline(retriever.vector_store, retriever.embedding_service)
    result = pipeline.run(args.corpus, reset=args.reset)
    get_bm25_search_engine().reindex(args.corpus)

    print("=" * 65)
    print("KNOWLEDGE INGESTION PIPELINE")
    print("=" * 65)
    print(f"* Status            : {result['status'].upper()}")
    print(f"* Total Documents   : {result['documents']}")
    print(f"* Total Chunks      : {result['chunks']}")
    print(f"* Embedding Model   : {result['embedding_model']}")
    print(f"* Vector Store      : {result['vector_store']}")
    print(f"* Chunking Strategy : {result['chunking_strategy']}")
    print(f"* Size / Overlap    : {result['chunk_size']} / {result['chunk_overlap']} characters")
    print(f"* Reset Existing DB : {args.reset}")
    print(f"* Execution Time    : {result['elapsed_seconds']}s")
    print("=" * 65)
