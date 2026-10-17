"""Check scenario policy coverage against the local corpus without network calls."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agents.roleplay.scenario_loader import ScenarioRepository  # noqa: E402
from src.integrations.practice_policy import (  # noqa: E402
    OfflinePolicyRetriever,
    ScenarioPolicyResolver,
    valid_policy_chunk,
)
from src.knowledge.validity import today_in_vietnam  # noqa: E402


def check_coverage(
    scenarios: ScenarioRepository, retriever: OfflinePolicyRetriever, target_date: date
) -> tuple[list[str], int]:
    rows = [f"Ngày đối chiếu: {target_date}", "Kịch bản | Chính sách | Kết quả"]
    missing = 0
    resolver = ScenarioPolicyResolver(retriever)
    for summary in scenarios.list_public():
        scenario = scenarios.get(summary.scenario_id)
        for expectation, policy in zip(
            scenario.policy_expectations, resolver.resolve(scenario, target_date), strict=True
        ):
            lookup = expectation.lookup
            matches = retriever.matching(
                lookup.query, product_model=lookup.product_model, document_type=lookup.document_type
            )
            matches = [
                chunk for chunk in matches if not lookup.policy_type or chunk.metadata.policy_type == lookup.policy_type
            ]
            active = [chunk for chunk in matches if valid_policy_chunk(chunk, target_date, lookup.query)]
            groups: dict[tuple, set[str]] = {}
            for chunk in active:
                meta = chunk.metadata
                groups.setdefault((meta.document_type, meta.product_model, meta.policy_type), set()).add(
                    chunk.document_id
                )
            if policy.status != "found":
                result = "⚠️ only expired sources / not_applicable" if matches else "❌ missing"
                missing += expectation.level == "expected"
            else:
                result = "✅ resolved " + "; ".join(
                    f"{source.document_id} v{source.version} valid until {source.valid_until or 'không giới hạn'}"
                    for source in policy.sources
                )
                if any(len(ids) >= 2 for ids in groups.values()):
                    result += " | ⚠️ conflicting active sources"
            rows.append(f"{scenario.scenario_id} | {expectation.policy_id} | {result}")
    return rows, int(missing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=today_in_vietnam())
    args = parser.parse_args(argv)
    retriever = OfflinePolicyRetriever([ROOT / "data/knowledge/corpus.json", ROOT / "data/knowledge/faq.json"])
    rows, missing = check_coverage(ScenarioRepository(), retriever, args.date)
    print("\n".join(rows))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
