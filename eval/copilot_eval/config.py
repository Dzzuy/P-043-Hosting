"""Run identity and write boundaries shared by every Copilot evaluation command."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_DATASET = REPO / "eval/datasets/copilot_benchmark.json"
DEFAULT_CORPUS = REPO / "data/knowledge/corpus.json"
DEFAULT_RUBRIC = Path(__file__).with_name("benchmark_rubric.md")
DEFAULT_CALIBRATION = Path(__file__).with_name("fixtures") / "development-calibration.json"


def writable(path: Path) -> Path:
    """Reject writes into closed evaluations, including through symlinks."""
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if any((parent / marker).is_file() for marker in ("completion-verification.json", "CLOSED")):
            raise ValueError(f"Closed evaluation is read-only: {parent}")
    return path


def case_path(directory: Path, case_id: str, suffix: str = ".json") -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", case_id):
        raise ValueError(f"Unsafe case ID: {case_id!r}")
    return directory / (case_id + suffix)


@dataclass(frozen=True)
class RunConfig:
    run_dir: Path
    project: str
    dataset: Path = DEFAULT_DATASET
    corpus: Path = DEFAULT_CORPUS
    rubric: Path = DEFAULT_RUBRIC
    calibration: Path = DEFAULT_CALIBRATION
    judge_model: str = DEFAULT_MODEL
    suite: str = "benchmark"

    def __post_init__(self):
        for key in ("run_dir", "dataset", "corpus", "rubric", "calibration"):
            object.__setattr__(self, key, Path(getattr(self, key)).resolve())
        if not self.project.strip() or not self.judge_model.strip():
            raise ValueError("Project and judge model must be explicit nonempty values")
        if self.suite not in {"benchmark", "development", "repetition"}:
            raise ValueError("Unknown evaluation suite")

    def paths(self):
        return {k: str(getattr(self, k)) for k in ("dataset", "corpus", "rubric", "calibration")}

    @classmethod
    def load(cls, run_dir: Path):
        run_dir = Path(run_dir).resolve()
        path = run_dir / "manifest.json"
        if not path.exists():
            path = run_dir / "preflight/config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            run_dir=run_dir,
            project=data["project"],
            judge_model=data["judge_model"],
            suite=data.get("suite", "benchmark"),
            **{k: data[k] for k in ("dataset", "corpus", "rubric", "calibration")},
        )


def matched_outcomes(cases, rows):
    """No zip truncation, duplicate outcomes, missing cases or reordering."""
    expected = [c["case_id"] for c in cases]
    actual = [r["case_id"] for r in rows]
    if len(set(expected)) != len(expected) or actual != expected:
        raise ValueError("Expected exactly one outcome per case, in dataset order")
    return list(zip(cases, rows, strict=True))
