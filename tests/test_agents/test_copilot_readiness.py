"""Read storage directly: provenance and tampering must fail closed."""

import json
from types import SimpleNamespace

import pytest

from src.knowledge import index_readiness as readiness
from src.knowledge.vector_store import ChromaVectorStore, InMemoryVectorStore


@pytest.fixture
def index(tmp_path):
    snapshot = readiness.load_snapshot()
    store = InMemoryVectorStore()
    chunks = list(snapshot.chunks.values())
    store.upsert_chunks(chunks, [[0.1, 0.2] for _ in chunks])
    settings = SimpleNamespace(
        vector_store_type="memory",
        chroma_collection_name="test",
        knowledge_manifest_dir=str(tmp_path),
        embedding_provider="hash",
        embedding_model_name="test-model",
    )
    readiness.write_manifest(store, snapshot, settings)
    return store, snapshot, settings


def test_original_corpus_exact_fields_and_float32_checksum(index):
    store, snapshot, settings = index
    assert len(type(snapshot.documents[0]).model_fields) == 12
    assert readiness.verify_index(store, snapshot, settings)["chunks"] == len(snapshot.chunks)
    original = readiness.inspect_records(store, snapshot)["checksum"]
    # Storage backends return float32 or Python doubles; canonical checksums agree.
    import struct

    for cid, vector in store._embeddings.items():
        store._embeddings[cid] = list(struct.unpack("<2f", struct.pack("<2f", *vector)))
    assert readiness.inspect_records(store, snapshot)["checksum"] == original


@pytest.mark.parametrize("mutation", ["missing", "extra", "content", "metadata", "vector", "nan", "dimensions"])
def test_index_tampering_is_not_ready(index, mutation):
    store, snapshot, settings = index
    cid = next(iter(store._chunks))
    if mutation == "missing":
        store._chunks.pop(cid)
    elif mutation == "extra":
        extra = store._chunks[cid].model_copy(deep=True)
        extra.chunk_id = "extra"
        store._chunks["extra"] = extra
        store._embeddings["extra"] = [0.1, 0.2]
    elif mutation == "content":
        store._chunks[cid].content += "changed"
    elif mutation == "metadata":
        store._chunks[cid].metadata.version = "different"
    elif mutation == "vector":
        store._embeddings[cid] = [0.3, 0.4]
    elif mutation == "nan":
        store._embeddings[cid] = [float("nan"), 0.2]
    elif mutation == "dimensions":
        store._embeddings[cid] = [0.1]
    with pytest.raises(readiness.IndexNotReadyError):
        readiness.verify_index(store, snapshot, settings)


@pytest.mark.parametrize("mutation", ["missing", "checksum", "provider", "model", "chunking", "corpus"])
def test_manifest_provenance_is_required(index, mutation):
    store, snapshot, settings = index
    path = readiness.manifest_path(settings)
    manifest = json.loads(path.read_text())
    if mutation == "missing":
        path.unlink()
    else:
        if mutation == "checksum":
            manifest["checksum"] = "wrong"
        elif mutation in {"provider", "model"}:
            manifest["embedding"][mutation] = "wrong"
        elif mutation == "chunking":
            manifest["chunking"]["size"] = 900
        else:
            manifest["corpus_sha256"] = "wrong"
        path.write_text(json.dumps(manifest))
    with pytest.raises(readiness.IndexNotReadyError):
        readiness.verify_index(store, snapshot, settings)


def test_chroma_uncached_audit_detects_stale_cache(index, tmp_path, monkeypatch):
    store, snapshot, settings = index
    import src.knowledge.vector_store as module

    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(chroma_persist_dir=str(tmp_path / "chroma"), chroma_collection_name="readiness-test"),
    )
    chroma = ChromaVectorStore()
    settings.vector_store_type = "chroma"
    settings.chroma_collection_name = "readiness-test"
    chunks = list(snapshot.chunks.values())
    chroma.upsert_chunks(chunks, [[0.1, 0.2] for _ in chunks])
    readiness.write_manifest(chroma, snapshot, settings)
    cid = chunks[0].chunk_id
    assert chroma.get_by_id(cid).content == chunks[0].content
    chroma.collection.update(ids=[cid], documents=["changed in storage"], embeddings=[[0.1, 0.2]])
    # This cached getter remains stale, while readiness must use storage.
    assert chroma.get_by_id(cid).content == chunks[0].content
    with pytest.raises(readiness.IndexNotReadyError, match="content/metadata"):
        readiness.verify_index(chroma, snapshot, settings)


def test_postgres_reads_vectors_and_metadata_without_schema_change(index, monkeypatch):
    from src.knowledge.pgvector_store import PgVectorStore

    store, snapshot, _ = index
    chunk = next(iter(snapshot.chunks.values()))
    rows = [(chunk.chunk_id, chunk.content, chunk.metadata.model_dump(mode="json", exclude_none=True), "[0.1,0.2]")]
    seen = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, parameters):
            seen.append(sql)
            return SimpleNamespace(fetchall=lambda: rows)

    backend = object.__new__(PgVectorStore)
    backend.collection_name = "test"
    monkeypatch.setattr(backend, "_connect", Connection)
    records = backend.read_records()
    assert readiness.canonical_chunk(records[0][0]) == readiness.canonical_chunk(chunk)
    assert records[0][1] == [0.1, 0.2]
    assert "embedding::text" in seen[0] and all("ALTER" not in sql for sql in seen)


def test_bm25_snapshot_is_verified(index, monkeypatch):
    store, snapshot, settings = index
    monkeypatch.setattr("src.config.get_settings", lambda: settings)
    monkeypatch.setattr(
        "src.knowledge.retrieval_service.get_retrieval_service", lambda: SimpleNamespace(vector_store=store)
    )
    monkeypatch.setattr("src.agents.copilot.tools.get_bm25_search_engine", lambda: SimpleNamespace(_chunks=[]))
    with pytest.raises(readiness.IndexNotReadyError, match="BM25"):
        readiness.check_copilot_index()


def test_failed_manifest_verification_never_replaces_previous(index, monkeypatch):
    store, snapshot, settings = index
    path = readiness.manifest_path(settings)
    before = path.read_bytes()
    store._chunks.pop(next(iter(store._chunks)))
    with pytest.raises(readiness.IndexNotReadyError):
        readiness.write_manifest(store, snapshot, settings)
    assert path.read_bytes() == before


def test_stale_cache_cannot_pass_even_when_storage_matches(index):
    store, snapshot, settings = index
    cid = next(iter(snapshot.chunks))
    stale = snapshot.chunks[cid].model_copy(deep=True)
    stale.metadata.version = "old cached version"
    store._cache = {cid: stale}
    with pytest.raises(readiness.IndexNotReadyError, match="cache"):
        readiness.verify_index(store, snapshot, settings)


def test_manifest_cannot_stamp_the_wrong_backend(index):
    store, snapshot, settings = index
    settings.vector_store_type = "chroma"
    with pytest.raises(readiness.IndexNotReadyError, match="backend"):
        readiness.write_manifest(store, snapshot, settings)


def test_app_liveness_survives_knowledge_initialization_failure(tmp_path):
    import os
    import subprocess
    import sys

    script = """
import asyncio
from httpx import ASGITransport, AsyncClient
import src.knowledge.retrieval_service as retrieval
def unavailable():
    raise RuntimeError('knowledge storage offline')
retrieval.get_retrieval_service = unavailable
from src.main import app
async def check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/health')).status_code == 200
        assert (await client.get('/ready')).status_code == 503
asyncio.run(check())
print('liveness ready')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'liveness.db'}"},
    )
    assert result.returncode == 0, result.stderr
    assert "liveness ready" in result.stdout
