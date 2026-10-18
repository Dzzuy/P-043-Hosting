import copy
import json
from datetime import date
from typing import get_args

import pytest

from eval.roleplay_eval import evidence_recall
from src.agents.roleplay.contracts import ClaimCategory
from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk


class FixedRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def retrieve(self, query, *, top_k=4, product_model=None, document_type=None, target_date=None):
        self.calls.append((query, document_type))
        return list(self.chunks)


@pytest.fixture
def tiny_dataset(tmp_path):
    real = evidence_recall.validate()
    document = real["probes"][0]["expected"][0]
    split = next(p for p in real["probes"] if p["probe_id"] == "S01_ON_FACT_FAST_CHARGE#0")["expected"][0]
    missing = next(p for p in real["probes"] if p["probe_id"] == "S01_ON_FACT_VF5_BATTERY_CAPACITY#0")["expected"][0]
    probes = [
        {
            "probe_id": identifier,
            "source": source,
            "scenario_id": "SCENARIO_01_VF5_TAXI",
            "claim_text": "Thông tin kỹ thuật VF 5",
            "expected": expected,
        }
        for identifier, source, expected in [
            ("direct", "golden", [document]),
            ("split", "paraphrase", [split]),
            ("partial", "paraphrase", [document, missing]),
        ]
    ]
    data = {"categories": real["categories"], "probes": probes}
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    contents = [document["quote"], split["quote"][:20], split["quote"][20:]]
    chunks = []
    for index, content in enumerate(contents):
        chunk_id = f"{document['document_id']}_{index}"
        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk_id,
                document_id=document["document_id"],
                content=content,
                metadata=ChunkMetadata(
                    chunk_id=chunk_id,
                    document_id=document["document_id"],
                    title="Test source",
                    document_type="product_specs",
                    product_model="VF 5",
                    effective_date=date(2026, 1, 1),
                    source="https://example.test/specs",
                    version=document["version"],
                ),
            )
        )
    return path, FixedRetriever(chunks)


def test_real_dataset_validates():
    data = evidence_recall.validate()
    assert evidence_recall.claim_categories() == get_args(ClaimCategory)
    assert len(data["categories"]) == 7
    assert {p["source"] for p in data["probes"]} == {"golden", "paraphrase"}


@pytest.mark.parametrize("mutation", ["category", "scenario", "version", "quote", "duplicate", "source", "empty"])
def test_validation_rejects_invalid_probes(tiny_dataset, mutation):
    path, _ = tiny_dataset
    data = json.loads(path.read_text())
    probe = data["probes"][0]
    if mutation == "category":
        data["categories"][0] = "invented"
    elif mutation == "scenario":
        probe["scenario_id"] = "missing"
    elif mutation in {"version", "quote"}:
        probe["expected"][0][mutation] = "missing"
    elif mutation == "duplicate":
        data["probes"].append(copy.deepcopy(probe))
    elif mutation == "source":
        probe["source"] = "invented"
    else:
        probe["expected"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        evidence_recall.validate(path)


def test_validation_rejects_repeated_quote(tiny_dataset, tmp_path):
    path, _ = tiny_dataset
    data = json.loads(path.read_text())
    data["probes"] = data["probes"][:1]
    path.write_text(json.dumps(data), encoding="utf-8")
    document = data["probes"][0]["expected"][0]
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps([{**document, "content": document["quote"] * 2}]), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly once"):
        evidence_recall.validate(path, corpus_path=corpus)


def test_provider_cells_and_metrics(tiny_dataset):
    path, retriever = tiny_dataset
    data = evidence_recall.validate(path)
    report = evidence_recall.execute(data, data["probes"], retriever, general_top_k=0)
    assert len(report["cells"]) == 21
    for cell in report["cells"]:
        passed = cell["category"] != "price" and cell["probe_id"] != "partial"
        assert cell["passed"] is passed
        assert cell["evidence_count"] == (0 if cell["category"] == "price" else 3)
        assert cell["evidence_source_ids"] == (
            [] if cell["category"] == "price" else [c.chunk_id for c in retriever.chunks]
        )
        if cell["probe_id"] == "partial" and cell["category"] != "price":
            assert [e["found"] for e in cell["expected"]] == [True, False]
    metrics = report["metrics"]
    assert metrics["overall"] == {"cells": 21, "passing_cells": 12, "recall": 12 / 21, "mean_evidence_chunks": 54 / 21}
    assert metrics["by_category"]["price"]["recall"] == 0
    assert metrics["by_category"]["other"]["recall"] == 2 / 3
    assert metrics["by_source"]["golden"]["recall"] == 6 / 7
    assert metrics["by_source"]["paraphrase"]["recall"] == 3 / 7
    assert metrics["by_probe"]["split"]["recall"] == 6 / 7
    assert metrics["by_probe"]["partial"]["recall"] == 0
    assert "| split | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |" in evidence_recall.markdown(report)


def test_matches_require_expected_document(tiny_dataset):
    path, retriever = tiny_dataset
    data = evidence_recall.validate(path)
    for chunk in retriever.chunks:
        chunk.chunk_id = "unrelated_" + chunk.chunk_id
    report = evidence_recall.execute(data, data["probes"], retriever, general_top_k=0)
    assert report["metrics"]["by_probe"]["split"]["recall"] == 0
    assert report["metrics"]["by_probe"]["direct"]["recall"] == 0


def test_cli_selection_reports_and_output_protection(tiny_dataset, tmp_path, monkeypatch):
    path, retriever = tiny_dataset
    execute = evidence_recall.execute
    calls = []

    def offline_execute(data, probes):
        calls.append([p["probe_id"] for p in probes])
        return execute(data, probes, retriever, general_top_k=0)

    monkeypatch.setattr(evidence_recall, "execute", offline_execute)
    output = tmp_path / "report.json"
    args = ["--dataset", str(path), "--mode", "run", "--probe-id", "direct", "split", "--output", str(output)]
    assert evidence_recall.main(args) == 1
    assert calls == [["direct", "split"]]
    report = json.loads(output.read_text())
    assert len(report["cells"]) == 14
    assert output.with_suffix(".md").read_text() == evidence_recall.markdown(report)
    assert evidence_recall.main(args) == 2
    assert len(calls) == 1
    assert evidence_recall.main(["--dataset", str(path), "--probe-id", "missing"]) == 2
    assert evidence_recall.main(["--dataset", str(path), "--probe-id", "direct", "--probe-id", "split"]) == 0
    assert len(calls) == 1  # Validation never constructs or calls a retriever.


def test_empty_aggregate():
    assert evidence_recall.aggregate([]) == {
        "cells": 0,
        "passing_cells": 0,
        "recall": None,
        "mean_evidence_chunks": None,
    }
