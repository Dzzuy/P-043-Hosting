import logging
import math
from abc import ABC, abstractmethod
from typing import Any

from src.config import get_settings
from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk
from src.observability import span

logger = logging.getLogger(__name__)


class BaseVectorStore(ABC):
    """Abstract Vector Store Interface (Adapter Pattern)."""

    @abstractmethod
    def upsert_chunks(self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]) -> None:
        """Add or update chunks with their embeddings in the vector database."""
        pass

    @abstractmethod
    def similarity_search_with_scores(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        """Query top-K similar chunks matching optional metadata filter with cosine similarity scores."""
        pass

    @abstractmethod
    def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[KnowledgeChunk]:
        """Query top-K similar chunks matching optional metadata filter."""
        pass

    @abstractmethod
    def get_by_id(self, chunk_id: str) -> KnowledgeChunk | None:
        """Fetch single chunk by its ID."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Total chunks in the store."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Clear all stored vectors."""
        pass

    def read_records(self) -> list[tuple[KnowledgeChunk, list[float]]]:
        """Read the entire collection from storage, never through the chunk cache."""
        raise NotImplementedError("This store cannot verify index integrity")


class InMemoryVectorStore(BaseVectorStore):
    """Lightweight in-memory vector store for unit tests and local execution."""

    def __init__(self):
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._embeddings: dict[str, list[float]] = {}

    def upsert_chunks(self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]) -> None:
        for chunk, emb in zip(chunks, embeddings):
            self._chunks[chunk.chunk_id] = chunk
            self._embeddings[chunk.chunk_id] = emb

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def similarity_search_with_scores(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        candidates: list[tuple[float, KnowledgeChunk]] = []

        for cid, chunk in self._chunks.items():
            emb = self._embeddings.get(cid)
            if not emb:
                continue

            # Apply metadata filter
            if where:
                match = True
                for k, v in where.items():
                    chunk_val = getattr(chunk.metadata, k, None)
                    if hasattr(chunk_val, "value"):
                        chunk_val = chunk_val.value
                    if isinstance(v, (list, tuple, set)):
                        if str(chunk_val) not in [str(x) for x in v]:
                            match = False
                            break
                    elif isinstance(v, dict) and "$in" in v:
                        if str(chunk_val) not in [str(x) for x in v["$in"]]:
                            match = False
                            break
                    elif str(chunk_val) != str(v):
                        match = False
                        break
                if not match:
                    continue

            score = self._cosine_similarity(query_embedding, emb)
            candidates.append((score, chunk))

        # Sort descending by score
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [(c[1], c[0]) for c in candidates[:top_k]]

    def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[KnowledgeChunk]:
        return [chunk for chunk, _ in self.similarity_search_with_scores(query_embedding, top_k, where)]

    def get_by_id(self, chunk_id: str) -> KnowledgeChunk | None:
        return self._chunks.get(chunk_id)

    def count(self) -> int:
        return len(self._chunks)

    def read_records(self):
        return [(chunk.model_copy(deep=True), list(self._embeddings[cid])) for cid, chunk in self._chunks.items()]

    def reset(self) -> None:
        self._chunks.clear()
        self._embeddings.clear()


class ChromaVectorStore(BaseVectorStore):
    """Production baseline vector store using persistent ChromaDB."""

    def __init__(self, persist_dir: str | None = None, collection_name: str | None = None):
        import chromadb

        settings = get_settings()
        self.persist_dir = persist_dir or settings.chroma_persist_dir
        self.collection_name = collection_name or settings.chroma_collection_name

        with span("db.connect", backend="chroma"):
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        self._cache: dict[str, KnowledgeChunk] = {}

    def _serialize_metadata(self, meta: ChunkMetadata) -> dict[str, Any]:
        result = {}
        for k, v in meta.model_dump().items():
            if v is None:
                continue
            if hasattr(v, "isoformat"):
                result[k] = v.isoformat()
            elif hasattr(v, "value"):
                result[k] = v.value
            elif isinstance(v, (int, float, bool)):
                result[k] = v
            else:
                result[k] = str(v)
        return result

    def upsert_chunks(self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return

        ids = [c.chunk_id for c in chunks]
        docs = [c.content for c in chunks]
        metadatas = [self._serialize_metadata(c.metadata) for c in chunks]

        self.collection.upsert(
            ids=ids,
            documents=docs,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        for c in chunks:
            self._cache[c.chunk_id] = c

    def similarity_search_with_scores(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        chroma_where = None
        if where:
            clean_where = {}
            for k, v in where.items():
                if v is None:
                    continue
                if isinstance(v, (list, tuple, set)):
                    clean_where[k] = {"$in": [x.value if hasattr(x, "value") else str(x) for x in v]}
                elif isinstance(v, dict):
                    clean_where[k] = v
                elif hasattr(v, "value"):
                    clean_where[k] = v.value
                else:
                    clean_where[k] = str(v)

            if len(clean_where) == 1:
                chroma_where = clean_where
            elif len(clean_where) > 1:
                chroma_where = {"$and": [{k: v} for k, v in clean_where.items()]}

        with span("db.execute", backend="chroma", operation="search", top_k=top_k):
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=chroma_where,
                include=["metadatas", "documents", "distances"],
            )

        matched: list[tuple[KnowledgeChunk, float]] = []
        if results and results.get("ids") and len(results["ids"]) > 0:
            ids = results["ids"][0]
            distances = results.get("distances", [[]])[0] if results.get("distances") else []
            for i, chunk_id in enumerate(ids):
                chunk = self.get_by_id(chunk_id)
                if chunk:
                    dist = distances[i] if i < len(distances) else 1.0
                    sim = 1.0 - dist
                    matched.append((chunk, sim))

        return matched

    def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[KnowledgeChunk]:
        return [chunk for chunk, _ in self.similarity_search_with_scores(query_embedding, top_k, where)]

    def get_by_id(self, chunk_id: str) -> KnowledgeChunk | None:
        if chunk_id in self._cache:
            return self._cache[chunk_id]

        with span("db.execute", backend="chroma", operation="get_by_id"):
            res = self.collection.get(ids=[chunk_id], include=["metadatas", "documents"])
        if res and res.get("ids") and len(res["ids"]) > 0:
            content = res["documents"][0] if res.get("documents") else ""
            meta_dict = res["metadatas"][0] if res.get("metadatas") else {}
            metadata = ChunkMetadata.model_validate(meta_dict)
            chunk = KnowledgeChunk(
                chunk_id=chunk_id,
                document_id=metadata.document_id,
                content=content,
                metadata=metadata,
            )
            self._cache[chunk_id] = chunk
            return chunk
        return None

    def count(self) -> int:
        with span("db.execute", backend="chroma", operation="count"):
            return self.collection.count()

    def read_records(self):
        records, offset = [], 0
        while True:
            with span("db.execute", backend="chroma", operation="read_records"):
                batch = self.collection.get(limit=256, offset=offset, include=["metadatas", "documents", "embeddings"])
            ids = batch.get("ids") or []
            if not ids:
                break
            for index, cid in enumerate(ids):
                raw = batch["metadatas"][index]
                if set(raw) - set(ChunkMetadata.model_fields):
                    raise ValueError("Unexpected stored metadata")
                metadata = ChunkMetadata.model_validate(raw)
                chunk = KnowledgeChunk(
                    chunk_id=cid, document_id=metadata.document_id, content=batch["documents"][index], metadata=metadata
                )
                records.append((chunk, [float(x) for x in batch["embeddings"][index]]))
            offset += len(ids)
        return records

    def reset(self) -> None:
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._cache.clear()


_vector_store_instance: BaseVectorStore | None = None


def get_vector_store() -> BaseVectorStore:
    """Use the configured backend without silently replacing a failed store."""
    global _vector_store_instance
    if _vector_store_instance is not None:
        return _vector_store_instance

    settings = get_settings()
    if settings.vector_store_type == "chroma":
        _vector_store_instance = ChromaVectorStore()
    elif settings.vector_store_type == "pgvector":
        from src.knowledge.pgvector_store import PgVectorStore

        _vector_store_instance = PgVectorStore(settings.database_url, settings.chroma_collection_name)
    else:
        _vector_store_instance = InMemoryVectorStore()
    return _vector_store_instance
