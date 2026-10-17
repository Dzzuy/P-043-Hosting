"""Validated access to the role-play scenario dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .contracts import EvaluationCriterion, ScenarioContract

DEFAULT_SCENARIO_PATH = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "scenarios.json"


class ScenarioDatasetError(ValueError):
    """Raised when the scenario dataset cannot be parsed or validated."""


class ScenarioNotFoundError(LookupError):
    """Raised when a requested scenario identifier is not in the dataset."""


class ScenarioSummary(BaseModel):
    """Advisor-safe scenario metadata used by a scenario picker."""

    scenario_id: str
    title: str
    difficulty: str
    target_skills: list[EvaluationCriterion]
    sales_channel: str | None = None
    training_objective: str | None = None
    scenario_version: str
    visible_context: str
    max_turns: int = Field(gt=0)
    voice_gender: Literal["male", "female"] | None = None
    outcome_labels: list[str] = Field(default_factory=list)

    @classmethod
    def from_scenario(cls, scenario: ScenarioContract) -> ScenarioSummary:
        return cls(
            scenario_id=scenario.scenario_id,
            title=scenario.title,
            difficulty=scenario.difficulty,
            target_skills=scenario.target_skills,
            sales_channel=scenario.sales_channel,
            training_objective=scenario.training_objective,
            scenario_version=scenario.scenario_version,
            visible_context=scenario.visible_context,
            max_turns=scenario.termination_conditions.max_turns,
            voice_gender=_voice_gender_from_name(scenario.persona.get("name", "")),
            outcome_labels=[outcome.label for outcome in scenario.acceptable_outcomes],
        )


def _voice_gender_from_name(name: str) -> Literal["male", "female"] | None:
    """Expose only the voice choice implied by a public Vietnamese title."""
    title = name.strip().split(" ", 1)[0].casefold()
    if title in {"anh", "ông", "chú"}:
        return "male"
    if title in {"chị", "cô", "bà"}:
        return "female"
    return None


class ScenarioRepository:
    """Load the complete dataset once and expose safe lookup operations."""

    def __init__(self, dataset_path: Path = DEFAULT_SCENARIO_PATH) -> None:
        self.dataset_path = dataset_path
        self._scenarios = self._load(dataset_path)

    @staticmethod
    def _load(dataset_path: Path) -> dict[str, ScenarioContract]:
        try:
            raw_dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ScenarioDatasetError(f"cannot load scenario dataset {dataset_path}: {exc}") from exc

        if not isinstance(raw_dataset, list):
            raise ScenarioDatasetError("scenario dataset root must be a JSON array")

        scenarios: dict[str, ScenarioContract] = {}
        for index, raw_scenario in enumerate(raw_dataset):
            try:
                scenario = ScenarioContract.model_validate(raw_scenario)
            except ValidationError as exc:
                raise ScenarioDatasetError(f"invalid scenario at index {index}: {exc}") from exc
            if scenario.scenario_id in scenarios:
                raise ScenarioDatasetError(f"duplicate scenario_id: {scenario.scenario_id}")
            scenarios[scenario.scenario_id] = scenario

        if not scenarios:
            raise ScenarioDatasetError("scenario dataset must contain at least one scenario")
        return scenarios

    def get(self, scenario_id: str) -> ScenarioContract:
        try:
            return self._scenarios[scenario_id].model_copy(deep=True)
        except KeyError as exc:
            raise ScenarioNotFoundError(f"unknown scenario_id: {scenario_id}") from exc

    def list_public(self) -> list[ScenarioSummary]:
        return [ScenarioSummary.from_scenario(scenario) for scenario in self._scenarios.values()]
