"""Strict contracts for provisional role-play evaluation and manager review."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class CriterionType(StrEnum):
    NEED_DISCOVERY = "need_discovery"
    PRODUCT_KNOWLEDGE = "product_knowledge"
    OBJECTION_HANDLING = "objection_handling"
    POLICY_ACCURACY = "policy_accuracy"
    CLOSING_NEXT_STEP = "closing_next_step"


class CriterionStatus(StrEnum):
    ASSESSED = "assessed"
    UNASSESSED = "unassessed"


class CheckVerdict(StrEnum):
    MET = "met"
    MISSED = "missed"
    NOT_APPLICABLE = "not_applicable"
    UNCLEAR = "unclear"


class FactualClaimStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"


class ReviewStatus(StrEnum):
    AI_DRAFT = "ai_draft"
    PENDING_MANAGER_REVIEW = "pending_manager_review"
    MANAGER_APPROVED = "manager_approved"


class TranscriptEvidence(BaseModel):
    message_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class ObservableCheckResult(BaseModel):
    check_id: str = Field(min_length=1)
    verdict: CheckVerdict
    evidence: list[TranscriptEvidence] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class CriterionEvaluation(BaseModel):
    """Evidence-backed assessment for one rubric criterion."""

    criterion: CriterionType
    status: CriterionStatus
    score: int | None = Field(None, ge=1, le=3)
    checks: list[ObservableCheckResult] = Field(default_factory=list)
    evidence: list[TranscriptEvidence] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    improvement_suggestion: str | None = None

    @model_validator(mode="after")
    def validate_status_and_score(self) -> "CriterionEvaluation":
        if self.status is CriterionStatus.ASSESSED:
            if self.score is None:
                raise ValueError("assessed criterion requires a score")
            if not self.evidence:
                raise ValueError("assessed criterion requires transcript evidence")
        elif self.score is not None:
            raise ValueError("unassessed criterion must not contain a score")
        return self


class KnowledgeEvidenceReference(BaseModel):
    source_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class FactualFinding(BaseModel):
    claim: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    status: FactualClaimStatus
    source_ids: list[str] = Field(default_factory=list)
    source_references: list[KnowledgeEvidenceReference] = Field(default_factory=list)
    severity: str = Field(default="info", pattern="^(info|warning|critical)$")
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_references(self) -> "FactualFinding":
        reference_ids = [reference.source_id for reference in self.source_references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("factual source references must be unique")
        if self.source_ids and reference_ids and set(self.source_ids) != set(reference_ids):
            raise ValueError("source_ids must match source_references")
        if reference_ids and not self.source_ids:
            self.source_ids = reference_ids
        return self


class RecommendedNextPractice(BaseModel):
    type: str = Field(pattern="^(scenario|document)$")
    target_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SessionEvaluationResult(BaseModel):
    """Provisional AI evaluation for one completed practice attempt."""

    session_id: str
    scenario_id: str
    judge_model: str | None = None
    closing_outcome: str | None = None
    closing_outcome_label: str | None = None
    rubric_version: str = Field(min_length=1)
    assessed_criteria_count: int = Field(ge=0, le=5)
    overall_score: float | None = Field(None, ge=1.0, le=3.0)
    passed: bool | None = None
    evaluations: list[CriterionEvaluation] = Field(min_length=5, max_length=5)
    factual_findings: list[FactualFinding] = Field(default_factory=list)
    summary_strengths: list[str] = Field(default_factory=list)
    summary_weaknesses: list[str] = Field(default_factory=list)
    recommended_next_practice: RecommendedNextPractice | None = None
    review_status: ReviewStatus = ReviewStatus.AI_DRAFT

    @model_validator(mode="after")
    def validate_criteria_and_aggregate(self) -> "SessionEvaluationResult":
        criteria = [item.criterion for item in self.evaluations]
        if len(criteria) != len(set(criteria)):
            raise ValueError("criterion evaluations must be unique")

        assessed_scores = [
            item.score
            for item in self.evaluations
            if item.status is CriterionStatus.ASSESSED and item.score is not None
        ]
        if self.assessed_criteria_count != len(assessed_scores):
            raise ValueError("assessed_criteria_count does not match evaluations")
        if assessed_scores and self.overall_score is None:
            raise ValueError("overall_score is required when criteria are assessed")
        if assessed_scores and self.overall_score is not None:
            expected_score = sum(assessed_scores) / len(assessed_scores)
            if abs(self.overall_score - expected_score) > 1e-6:
                raise ValueError("overall_score must equal the mean of assessed criteria")
        if not assessed_scores and self.overall_score is not None:
            raise ValueError("overall_score must be null when no criteria are assessed")
        return self
