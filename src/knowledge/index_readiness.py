"""Storage audits and technical manifests, without adding corpus metadata."""

import hashlib
import json
import math
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.knowledge.chunking import CHUNK_OVERLAP, CHUNK_SIZE, chunk_document, chunking_identity
from src.knowledge.schemas import KnowledgeChunk, KnowledgeDocument
from src.observability import instrument


class IndexNotReadyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CorpusSnapshot:
    fingerprint: str
    documents: tuple[KnowledgeDocument, ...]
    chunks: dict[str, KnowledgeChunk]
    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP

    def catalog(self):
        return {
            name: sorted({getattr(doc, name) for doc in self.documents if getattr(doc, name) is not None})
            for name in ("product_model", "document_type", "policy_type")
        }


@instrument("readiness.snapshot")
def load_snapshot(path="data/knowledge/corpus.json", chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    raw = Path(path).read_bytes()
    records = json.loads(raw)
    if not isinstance(records, list) or not records:
        raise IndexNotReadyError("invalid corpus")
    if any(not isinstance(r, dict) or set(r) != set(KnowledgeDocument.model_fields) for r in records):
        raise IndexNotReadyError("corpus must keep its twelve fields")
    documents = tuple(KnowledgeDocument.model_validate(record) for record in records)
    if any(not doc.content.strip() or (doc.expiry_date and doc.expiry_date < doc.effective_date) for doc in documents):
        raise IndexNotReadyError("invalid document content or validity interval")
    if len({doc.document_id for doc in documents}) != len(documents):
        raise IndexNotReadyError("duplicate document IDs")
    chunks = [chunk for doc in documents for chunk in chunk_document(doc, chunk_size, chunk_overlap)]
    if not chunks or len({c.chunk_id for c in chunks}) != len(chunks):
        raise IndexNotReadyError("invalid chunk identities")
    return CorpusSnapshot(
        hashlib.sha256(raw).hexdigest(),
        documents,
        {chunk.chunk_id: chunk for chunk in chunks},
        chunk_size,
        chunk_overlap,
    )


def canonical_chunk(chunk):
    return json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


@instrument("readiness.integrity")
def inspect_records(store, snapshot):
    for cid, cached in list(getattr(store, "_cache", {}).items()):
        expected = snapshot.chunks.get(cid)
        if expected is None or canonical_chunk(cached) != canonical_chunk(expected):
            raise IndexNotReadyError("chunk cache differs from corpus snapshot")
    records = store.read_records()
    if len(records) != len(snapshot.chunks) or len({chunk.chunk_id for chunk, _ in records}) != len(records):
        raise IndexNotReadyError("missing, extra or duplicate chunks")
    digest, dimension = hashlib.sha256(), None
    for chunk, vector in sorted(records, key=lambda item: item[0].chunk_id):
        expected = snapshot.chunks.get(chunk.chunk_id)
        if expected is None or canonical_chunk(chunk) != canonical_chunk(expected):
            raise IndexNotReadyError("stored content/metadata differs from corpus")
        if not vector or any(not math.isfinite(v) for v in vector):
            raise IndexNotReadyError("invalid embedding")
        if dimension is None:
            dimension = len(vector)
        if len(vector) != dimension:
            raise IndexNotReadyError("inconsistent vector dimensions")
        encoded = canonical_chunk(chunk)
        digest.update(struct.pack("<I", len(encoded)))
        digest.update(encoded)
        try:
            digest.update(struct.pack(f"<{len(vector)}f", *vector))
        except (OverflowError, struct.error) as exc:
            raise IndexNotReadyError("invalid float32 embedding") from exc
    return {"dimensions": dimension, "checksum": digest.hexdigest(), "chunks": len(records)}


def manifest_path(settings):
    identity = f"{settings.vector_store_type}:{settings.chroma_collection_name}"
    name = hashlib.sha256(identity.encode()).hexdigest()[:24] + ".json"
    return Path(settings.knowledge_manifest_dir) / name


def embedding_identity(settings):
    model = settings.embedding_model_name
    if settings.embedding_provider == "openrouter" and "/" not in model:
        model = "openai/" + model
    return {"provider": settings.embedding_provider, "model": model}


def validate_backend(store, settings):
    from src.knowledge.pgvector_store import PgVectorStore
    from src.knowledge.vector_store import ChromaVectorStore, InMemoryVectorStore

    expected = {"memory": InMemoryVectorStore, "chroma": ChromaVectorStore, "pgvector": PgVectorStore}
    if not isinstance(store, expected[settings.vector_store_type]):
        raise IndexNotReadyError("configured storage backend mismatch")
    if settings.vector_store_type != "memory" and store.collection_name != settings.chroma_collection_name:
        raise IndexNotReadyError("configured collection mismatch")


def write_manifest(store, snapshot, settings, *, chunk_size=None, chunk_overlap=None):
    validate_backend(store, settings)
    chunk_size = snapshot.chunk_size if chunk_size is None else chunk_size
    chunk_overlap = snapshot.chunk_overlap if chunk_overlap is None else chunk_overlap
    if (chunk_size, chunk_overlap) != (snapshot.chunk_size, snapshot.chunk_overlap):
        raise IndexNotReadyError("manifest chunking differs from snapshot")
    manifest = {
        "format": 2,
        "corpus_sha256": snapshot.fingerprint,
        "chunking": chunking_identity(chunk_size, chunk_overlap),
        "embedding": embedding_identity(settings),
        "store": {"type": settings.vector_store_type, "collection": settings.chroma_collection_name},
        **inspect_records(store, snapshot),
    }
    target = manifest_path(settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="manifest-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return manifest


def verify_index(store, snapshot, settings):
    validate_backend(store, settings)
    target = manifest_path(settings)
    if not target.is_file():
        raise IndexNotReadyError("manifest missing; explicit reindex required")
    manifest = json.loads(target.read_text(encoding="utf-8"))
    if manifest.get("format") != 2:
        raise IndexNotReadyError("chunking format changed; explicit reindex into a new collection required")
    if manifest.get("corpus_sha256") != snapshot.fingerprint:
        raise IndexNotReadyError("manifest/corpus mismatch")
    if manifest.get("embedding") != embedding_identity(settings):
        raise IndexNotReadyError("embedding provenance mismatch")
    if manifest.get("store") != {"type": settings.vector_store_type, "collection": settings.chroma_collection_name}:
        raise IndexNotReadyError("manifest/store mismatch")
    if manifest.get("chunking") != chunking_identity(snapshot.chunk_size, snapshot.chunk_overlap):
        raise IndexNotReadyError("chunking configuration mismatch")
    measured = inspect_records(store, snapshot)
    if any(manifest.get(key) != value for key, value in measured.items()):
        raise IndexNotReadyError("index checksum mismatch")
    return measured


_cached_verified_snapshot = None


def check_copilot_index():
    from src.agents.copilot.tools import get_bm25_search_engine
    from src.config import get_settings
    from src.knowledge.retrieval_service import get_retrieval_service

    global _cached_verified_snapshot
    if _cached_verified_snapshot is not None:
        return _cached_verified_snapshot

    try:
        settings = get_settings()
        snapshot = load_snapshot()
        verify_index(get_retrieval_service().vector_store, snapshot, settings)
        sparse = get_bm25_search_engine()
        if {c.chunk_id: canonical_chunk(c) for c in sparse._chunks} != {
            cid: canonical_chunk(c) for cid, c in snapshot.chunks.items()
        }:
            raise IndexNotReadyError("BM25 snapshot mismatch")
        _cached_verified_snapshot = snapshot
        return snapshot
    except IndexNotReadyError:
        _cached_verified_snapshot = None
        raise
    except Exception as exc:
        _cached_verified_snapshot = None
        raise IndexNotReadyError("index verification unavailable") from exc

