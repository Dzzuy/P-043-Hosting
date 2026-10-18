"""Chunk quality and migration checks, without a provider or live index."""

import json
from types import SimpleNamespace

import pytest

from src.agents.copilot.tools import BM25SearchEngine, _make_hit, build_evidence_context
from src.knowledge.chunking import CHUNK_SIZE, chunk_document, chunk_embedding_text, chunking_identity
from src.knowledge.embedding import KnowledgeEmbeddingService
from src.knowledge.index_readiness import (
    IndexNotReadyError,
    canonical_chunk,
    load_snapshot,
    manifest_path,
    verify_index,
    write_manifest,
)
from src.knowledge.ingestion import KnowledgeIngestionPipeline
from src.knowledge.schemas import KnowledgeDocument
from src.knowledge.vector_store import InMemoryVectorStore


def document(content, kind="product_specs"):
    return KnowledgeDocument(
        document_id="DOC",
        title="Tài liệu VF 5",
        document_type=kind,
        product_model="VF 5",
        effective_date="2026-09-22",
        source="test-source",
        content=content,
    )


def corpus_file(tmp_path, doc):
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps([doc.model_dump(mode="json")], ensure_ascii=False), encoding="utf-8")
    return path


def assert_verbatim_coverage(doc, chunks, size=CHUNK_SIZE):
    covered = set()
    for chunk in chunks:
        start, end = chunk.metadata.start_char, chunk.metadata.end_char
        assert chunk.content == doc.content[start:end]
        assert 0 < len(chunk.content) <= size
        covered.update(range(start, end))
    assert all(index in covered for index, char in enumerate(doc.content) if not char.isspace())


def test_overlap_never_leaves_a_spec_value_without_its_label():
    doc = document(
        "Giới thiệu sản phẩm. " * 32
        + "\n\nDung lượng pin khả dụng\n\n37,23 kWh\n\nLoại la-zăng\n\nHợp kim 17 inch\n\n"
        + "Mức tiêu thụ nhiên liệu công khai\n\n13 kWh/100 km\n\n"
        + "Tính năng giải trí. " * 32
    )
    chunks = chunk_document(doc)
    assert len(chunks) > 1
    assert_verbatim_coverage(doc, chunks)
    assert all("Dung lượng pin khả dụng" in chunk.content for chunk in chunks if "37,23 kWh" in chunk.content)
    assert all("Mức tiêu thụ nhiên liệu công khai" in chunk.content for chunk in chunks if "13 kWh" in chunk.content)


def test_reverse_value_unit_label_and_crlf_are_preserved():
    doc = document("  Thông số kỹ thuật\r\n\r\n170\r\n\r\nkW\r\n\r\nCông suất tối đa\r\n\r\n" + "Mô tả. " * 110)
    chunks = chunk_document(doc)
    assert_verbatim_coverage(doc, chunks)
    assert all("170\r\n\r\nkW\r\n\r\nCông suất tối đa" in c.content for c in chunks if "170" in c.content)


def test_price_rows_keep_headers_for_search_without_rewriting_citations():
    rows = [f"VF {index} | Plus | {index}.000.000 VNĐ" for index in range(3, 25)]
    doc = document(
        "A. Giá bán xe:\n\nGiá bán bán lẻ đề xuất kèm pin (bao gồm VAT)\n\nDòng xe | Phiên bản | Giá bán\n\n"
        + "\n\n".join(rows),
        "price_list",
    )
    chunks = chunk_document(doc)
    assert len(chunks) > 1
    assert_verbatim_coverage(doc, chunks)
    for row in rows:
        assert any(row in c.content for c in chunks)
    for chunk in chunks:
        assert "Dòng xe | Phiên bản | Giá bán" in chunk_embedding_text(chunk)
        assert "kèm pin" in chunk.metadata.section_title
    hit = _make_hit(chunks[-1], 1.0, 1, "bm25")
    context, citations = build_evidence_context([hit])
    assert hit["context_prefix"] in context
    assert citations[0].section == chunks[-1].metadata.section_title
    assert hit["content"] == chunks[-1].content
    assert citations[0].excerpt == hit["content"]  # Header metadata cannot replace verbatim source content.


def test_separate_policy_programs_never_overlap():
    first = "1. | Chương trình A:\n\na. | Đối tượng:\n\n- | Khách hàng nhóm A.\n\n- | Ưu đãi 3%."
    second = "2. | Chương trình B:\n\na. | Đối tượng:\n\n- | Khách hàng nhóm B.\n\n- | Ưu đãi 6%."
    doc = document(first + "\n\n" + second, "promotion")
    chunks = chunk_document(doc)
    assert_verbatim_coverage(doc, chunks)
    assert all(not ("nhóm A" in c.content and "nhóm B" in c.content) for c in chunks)
    assert all("Chương trình A" in c.metadata.section_title for c in chunks if "3%" in c.content)
    assert all("Chương trình B" in c.metadata.section_title for c in chunks if "6%" in c.content)


def test_headings_without_blank_lines_and_decimal_numbers():
    doc = document("# Pin\nDung lượng 37,23 kWh.\n# Sạc\nThời gian 33 phút.\nGiá 3.858 VNĐ/kWh.", "policy")
    chunks = chunk_document(doc)
    assert_verbatim_coverage(doc, chunks)
    assert len(chunks) == 2
    assert [c.metadata.section_title for c in chunks] == ["Pin", "Sạc"]
    assert "3.858" in chunks[1].content


def test_sibling_headings_and_wrapped_price_row_are_not_merged():
    doc = document("# Mục A\n\n# Mục B\n\nVàng (nóc trắng) | 11.000.000\n\ntrắng | VNĐ", "price_list")
    chunks = chunk_document(doc)
    assert [c.metadata.section_title for c in chunks] == ["Mục A", "Mục B"]
    assert "11.000.000\n\ntrắng | VNĐ" in chunks[1].content
    assert_verbatim_coverage(doc, chunks)


def test_wrapped_price_row_remains_whole_at_chunk_boundary():
    row = "Vàng (nóc trắng) | 11.000.000\n\ntrắng | VNĐ"
    doc = document("Giới thiệu. " * 60 + "\n\n" + row, "price_list")
    chunks = chunk_document(doc)
    assert len(chunks) > 1
    assert all(row in c.content for c in chunks if "11.000.000" in c.content or "trắng | VNĐ" in c.content)
    assert_verbatim_coverage(doc, chunks)


def test_currency_on_its_own_line_stays_with_price_row():
    row = "Be (Pebble Beige) | 8.000.000\n\nVNĐ"
    doc = document("Giới thiệu. " * 60 + "\n\n" + row, "price_list")
    chunks = chunk_document(doc)
    assert all(row in c.content for c in chunks if "8.000.000" in c.content or "VNĐ" in c.content)
    assert_verbatim_coverage(doc, chunks)


def test_numbered_subsections_keep_article_or_letter_parent():
    for heading in ("Điều 1. Hợp đồng", "B. Trang bị"):
        doc = document(heading + "\n\n1. | Mục một:\n\nNội dung một.\n\n2. | Mục hai:\n\nNội dung hai.", "policy")
        chunks = chunk_document(doc)
        assert len(chunks) == 2
        assert all(heading in c.metadata.section_title for c in chunks)
        assert all(not ("Nội dung một" in c.content and "Nội dung hai" in c.content) for c in chunks)
        assert_verbatim_coverage(doc, chunks)


def test_wrapped_pdf_bullet_clause_stays_whole_at_chunk_boundary():
    clause = "- | Điều kiện áp dụng với khách hàng mua xe\n\ntrước ngày 10/02/2026 và có hóa đơn hợp lệ."
    doc = document("Giới thiệu. " * 56 + "\n\n" + clause, "policy")
    chunks = chunk_document(doc)
    assert len(chunks) > 1
    assert all(clause in c.content for c in chunks if "10/02/2026" in c.content)
    assert_verbatim_coverage(doc, chunks)


def test_oversized_clause_uses_recursive_fallback_and_keeps_source_offsets():
    doc = document(
        "Điều 1. Thanh toán\n\n"
        + "Khách hàng thanh toán theo hợp đồng. " * 100
        + "\n\nĐiều 2. Bàn giao\n\nNgày bàn giao phải được xác nhận.",
        "policy",
    )
    chunks = chunk_document(doc)
    assert_verbatim_coverage(doc, chunks)
    assert any(c.metadata.requires_context for c in chunks)
    assert all(not ("Điều 1." in c.content and "Điều 2." in c.content) for c in chunks)


@pytest.mark.parametrize("size,overlap", [(0, 0), (-1, 0), (750, -1), (100, 100), (100, 101)])
def test_invalid_chunk_configuration(size, overlap):
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_document(document("Thông số xe"), size, overlap)


def test_real_corpus_is_verbatim_reproducible_and_bm25_matches():
    snapshot = load_snapshot()
    assert len(KnowledgeDocument.model_fields) == 12
    for doc in snapshot.documents:
        chunks = [c for c in snapshot.chunks.values() if c.document_id == doc.document_id]
        assert_verbatim_coverage(doc, chunks)
        assert [canonical_chunk(c) for c in chunks] == [canonical_chunk(c) for c in chunk_document(doc)]
    sparse = BM25SearchEngine()
    assert {c.chunk_id: canonical_chunk(c) for c in sparse._chunks} == {
        cid: canonical_chunk(c) for cid, c in snapshot.chunks.items()
    }
    vf5 = [c for c in snapshot.chunks.values() if c.document_id == "SPECS_VF5_PLUS_2026"]
    assert all("Dung lượng pin khả dụng" in c.content for c in vf5 if "37,23 Kwh" in c.content)


def test_embedding_and_sparse_search_share_section_context(tmp_path):
    doc = document("Điều 1. Thanh toán\n\nKhách hàng thanh toán số tiền ghi trong hợp đồng.", "policy")
    chunks = chunk_document(doc)
    inputs = []
    service = object.__new__(KnowledgeEmbeddingService)
    service.embeddings = SimpleNamespace(
        embed_documents=lambda texts: inputs.extend(texts) or [[0.1, 0.2] for _ in texts]
    )
    service.embed_chunks(chunks)
    assert inputs == [chunk_embedding_text(c) for c in chunks]
    assert _make_hit(chunks[0], 1.0, 1, "dense")["section"] == "Điều 1. Thanh toán"
    engine = BM25SearchEngine(corpus_file(tmp_path, doc))
    assert engine._chunks[0].metadata.section_title == chunks[0].metadata.section_title


def settings_for_test(tmp_path):
    return SimpleNamespace(
        vector_store_type="memory",
        chroma_collection_name="chunking-test",
        knowledge_manifest_dir=str(tmp_path),
        embedding_provider="hash",
        embedding_model_name="test",
    )


def test_custom_snapshot_configuration_and_legacy_manifest_rejection(tmp_path):
    settings = settings_for_test(tmp_path)
    snapshot = load_snapshot(chunk_size=600, chunk_overlap=80)
    store = InMemoryVectorStore()
    chunks = list(snapshot.chunks.values())
    store.upsert_chunks(chunks, [[0.1, 0.2] for _ in chunks])
    manifest = write_manifest(store, snapshot, settings)
    assert manifest["chunking"] == chunking_identity(600, 80)
    assert verify_index(store, snapshot, settings)["chunks"] == len(chunks)
    manifest["format"] = 1
    manifest_path(settings).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(IndexNotReadyError, match="reindex"):
        verify_index(store, snapshot, settings)


def test_ingestion_refuses_to_overwrite_old_index_before_embedding(tmp_path, monkeypatch):
    settings = settings_for_test(tmp_path)
    monkeypatch.setattr("src.knowledge.ingestion.get_settings", lambda: settings)
    snapshot = load_snapshot()
    store = InMemoryVectorStore()
    original = next(iter(snapshot.chunks.values()))
    store.upsert_chunks([original], [[0.1, 0.2]])
    calls = []
    embedder = SimpleNamespace(embed_chunks=lambda chunks: calls.append(chunks))
    manifest_path(settings).write_text(json.dumps({"format": 1, "chunking": {"size": 1000}}), encoding="utf-8")
    with pytest.raises(ValueError, match="new collection"):
        KnowledgeIngestionPipeline(store, embedder).run()
    assert not calls
    assert store.count() == 1
    assert store.get_by_id(original.chunk_id) == original


def test_ingestion_manifest_and_bm25_agree_after_build(tmp_path, monkeypatch):
    settings = settings_for_test(tmp_path)
    monkeypatch.setattr("src.knowledge.ingestion.get_settings", lambda: settings)
    store = InMemoryVectorStore()
    embedder = SimpleNamespace(
        provenance={"provider": "hash", "model": "test"},
        model_name="test",
        embed_chunks=lambda chunks: [[0.1, 0.2] for _ in chunks],
    )
    report = KnowledgeIngestionPipeline(store, embedder).run()
    snapshot = load_snapshot()
    assert (report["chunk_size"], report["chunk_overlap"], report["chunk_unit"]) == (750, 100, "characters")
    assert verify_index(store, snapshot, settings)["chunks"] == len(snapshot.chunks)
    assert store.count() == len(BM25SearchEngine()._chunks)
