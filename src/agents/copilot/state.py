"""Contracts for bounded agentic retrieval and grounded sales assistance."""

import re
from datetime import date
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

ABSTAIN_ANSWER = "Tôi không thể xác minh thông tin này từ nguồn tài liệu hiện có."
ReasonCode = Literal[
    "input_blocked",
    "out_of_scope",
    "insufficient_evidence",
    "policy_conflict",
    "budget_exhausted",
    "verification_failed",
    "retrieval_degraded",
]
FALLBACK_ANSWERS = {
    "input_blocked": "Yêu cầu này không thể được xử lý. Vui lòng gửi câu hỏi tư vấn xe phù hợp hoặc làm mới phiên.",
    "out_of_scope": "Copilot hỗ trợ sales tra cứu sản phẩm, chính sách, so sánh xe và chuẩn bị tư vấn từ tài liệu hiện có.",
    "insufficient_evidence": ABSTAIN_ANSWER,
    "policy_conflict": "Các nguồn hiện có chưa thống nhất; tôi chưa thể xác minh kết luận áp dụng cho trường hợp này.",
    "budget_exhausted": "Đã đạt giới hạn xử lý; tôi chưa thể xác minh đầy đủ câu trả lời. Vui lòng thu hẹp câu hỏi.",
    "verification_failed": "Câu trả lời chưa vượt qua kiểm tra với tài liệu nguồn. Vui lòng thử lại hoặc thu hẹp câu hỏi.",
    "retrieval_degraded": "Một phần tra cứu tạm thời chưa khả dụng; tôi chưa thể xác minh câu trả lời.",
}
RequirementId = Annotated[str, StringConstraints(strict=True, pattern=r"^R[1-9]\d*$")]
CitationId = Annotated[str, StringConstraints(strict=True, pattern=r"^C[1-9]\d*$")]
AnswerText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=12000)]
SuggestionText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500)]


class RetrievalHit(TypedDict):
    chunk_id: str
    document_id: str
    content: str
    title: str
    section: str | None
    context_prefix: NotRequired[str | None]
    requires_context: NotRequired[bool]
    page: int | None
    source_uri: str | None
    effective_from: str | None
    effective_to: str | None
    status: str
    version: str
    product_model: str
    document_type: str
    policy_type: str | None
    competitor_model: str | None
    citation_id: NotRequired[str]
    search_requirement_ids: NotRequired[list[str]]
    retrieval_method: Literal["dense", "bm25"]
    native_score: float
    rank: int


class FusedHit(RetrievalHit):
    dense_score: float | None
    bm25_score: float | None
    rrf_score: float


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    citation_id: CitationId
    chunk_id: str
    document_id: str
    title: str
    section: str | None = None
    page: int | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    source_uri: str | None = None
    product_model: str | None = None
    document_type: str | None = None
    version: str | None = None
    excerpt: str | None = None


class ProductInsight(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Literal["highlight", "policy"]
    product_model: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=2, max_length=160)
    summary: str = Field(min_length=2, max_length=500)
    citation: Citation | None = None
    insight_id: str | None = None
    variant: str | None = None
    essential_conditions: str | None = None
    advisory_hint: str | None = None
    applicability: Literal["confirmed", "conditional"] | None = None
    origin_message_id: str | None = None


class CopilotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["answered", "partial", "needs_clarification", "abstained"]
    answer: AnswerText
    citations: list[Citation] = Field(default_factory=list)
    product_insights: list[ProductInsight] = Field(default_factory=list, max_length=8)
    talking_points: list[SuggestionText] = Field(default_factory=list, max_length=3)
    suggested_message: SuggestionText | None = None
    suggested_next_question: SuggestionText | None = None
    sales_actions: list[SuggestionText] = Field(default_factory=list, max_length=3)
    missing_information: list[SuggestionText] = Field(default_factory=list, max_length=6)
    clarification_question: SuggestionText | None = None

    request_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")] | None = None
    reason_code: ReasonCode | None = None
    answer_kind: Literal["factual", "mixed", "coaching"] = "factual"

    @model_validator(mode="after")
    def check_status(self) -> "CopilotResponse":
        if self.status in {"answered", "partial"} and not self.citations and self.answer_kind != "coaching":
            raise ValueError("answered requires citations")
        if self.status == "partial" and not self.missing_information:
            raise ValueError("partial requires missing_information")
        if self.status == "answered" and self.missing_information:
            raise ValueError("answered cannot contain missing_information")
        if self.status in {"answered", "needs_clarification"} and self.reason_code:
            raise ValueError("successful/clarification responses cannot have reason_code")
        if self.status == "needs_clarification" and (
            not self.clarification_question
            or self.citations
            or self.product_insights
            or self.talking_points
            or self.suggested_message
            or self.suggested_next_question
            or self.sales_actions
            or self.answer != self.clarification_question
        ):
            raise ValueError("clarification requires only a question, without factual claims")
        if self.status != "needs_clarification" and self.clarification_question:
            raise ValueError("clarification_question requires needs_clarification")
        if self.status == "abstained" and (
            self.citations
            or self.product_insights
            or self.answer != FALLBACK_ANSWERS.get(self.reason_code or "insufficient_evidence")
            or self.talking_points
            or self.suggested_message
            or self.suggested_next_question
            or self.sales_actions
            or self.clarification_question
        ):
            raise ValueError("abstained requires the canonical message and no sales suggestions")
        return self


class VerbatimQuote(BaseModel):
    """Separate excerpts from one source; never imply omitted text was contiguous."""

    model_config = ConfigDict(extra="forbid", strict=True)
    citation_id: CitationId
    quote_parts: list[AnswerText] = Field(min_length=1, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_quote(cls, value):
        if isinstance(value, dict) and "quote" in value and "quote_parts" not in value:
            value = dict(value)
            value["quote_parts"] = [value.pop("quote")]
        return value

    @model_validator(mode="after")
    def bound_excerpt_length(self):
        if sum(len(part) for part in self.quote_parts) > 12000:
            raise ValueError("combined quote_parts exceed 12000 characters")
        return self


class EvidenceQuote(VerbatimQuote):
    pass


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GuardDecision(StrictContract):
    decision: Literal["allow", "block"]
    reason: Literal[
        "none", "instruction_override", "prompt_leak", "privilege_escalation", "tool_abuse", "citation_forgery"
    ]

    @model_validator(mode="after")
    def check_reason(self):
        if (self.decision == "allow") != (self.reason == "none"):
            raise ValueError("invalid guard reason")
        return self


class Requirement(StrictContract):
    requirement_id: RequirementId
    description: SuggestionText
    kind: Literal["fact", "advice", "external"] = "fact"


class SearchRequest(StrictContract):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]
    product_model: str | None = None
    document_type: Literal["product_specs", "battlecard", "price_list", "policy", "promotion"] | None = None
    policy_type: str | None = None

    @field_validator("product_model")
    @classmethod
    def canonical_model(cls, value):
        if value:
            match = re.search(r"\bVF[\s-]*(\d+)\b", value, re.I)
            return "VF " + match.group(1) if match else value
        return value


class PlannedSearch(SearchRequest):
    requirement_ids: list[RequirementId] = Field(min_length=1, max_length=6)


class SearchPlan(StrictContract):
    searches: list[PlannedSearch] = Field(min_length=1, max_length=3)


class IntakeDecision(StrictContract):
    guard_decision: GuardDecision
    task: Literal["knowledge", "comparison", "objection", "call_preparation"] = "knowledge"
    route: Literal["simple", "complex", "clarify", "out_of_scope", "blocked"]
    requirements: list[Requirement] = Field(default_factory=list, max_length=6)
    product_models: list[str] = Field(default_factory=list, max_length=6)
    simple_search: SearchRequest | None = None
    clarification_question: SuggestionText | None = None
    answer_kind: Literal["factual", "mixed", "coaching"] = "factual"

    @field_validator("product_models")
    @classmethod
    def canonical_models(cls, values):
        return list(dict.fromkeys(SearchRequest(query="normalize", product_model=v).product_model for v in values))

    @model_validator(mode="after")
    def check_route(self):
        if len({r.requirement_id for r in self.requirements}) != len(self.requirements):
            raise ValueError("duplicate requirements")
        if self.guard_decision.decision == "allow" and self.route in {"simple", "complex"} and not self.requirements:
            raise ValueError("retrieval requires requirements")
        if (
            self.route == "simple"
            and self.guard_decision.decision == "allow"
            and self.simple_search is None
            and self.answer_kind != "coaching"
        ):
            raise ValueError("simple requires one search")
        if self.route == "clarify" and not self.clarification_question:
            raise ValueError("clarification needs a question")
        return self


class GroundedClaim(StrictContract):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    requirement_ids: list[RequirementId] = Field(min_length=1, max_length=6)
    citation_ids: list[CitationId] = Field(min_length=1, max_length=8)


class GeneratedAnswer(StrictContract):
    claims: list[GroundedClaim] = Field(default_factory=list, max_length=12)
    missing_information: list[SuggestionText] = Field(default_factory=list, max_length=6)
    suggested_message: SuggestionText | None = None
    suggested_next_question: SuggestionText | None = None
    sales_actions: list[SuggestionText] = Field(default_factory=list, max_length=3)


VerificationError = Literal[
    "format",
    "citation",
    "unsupported_claim",
    "wrong_model",
    "wrong_unit",
    "wrong_number",
    "policy_condition",
    "missing_evidence",
    "policy_conflict",
    "unsafe_suggestion",
]


class ClaimVerdict(StrictContract):
    claim_index: int = Field(ge=0)
    status: Literal["supported", "unsupported", "uncertain"]
    error_codes: list[VerificationError] = Field(default_factory=list, max_length=3)
    feedback: Annotated[str, StringConstraints(max_length=300)] = ""


class GroundingVerdict(StrictContract):
    claim_verdicts: list[ClaimVerdict] = Field(default_factory=list, max_length=12)
    answered_requirement_ids: list[RequirementId] = Field(default_factory=list, max_length=6)
    missing_requirement_ids: list[RequirementId] = Field(default_factory=list, max_length=6)
    recovery: Literal["none", "regenerate", "read_context", "search", "clarify", "conflict"] = "none"
    anchor_citation_ids: list[CitationId] = Field(default_factory=list, max_length=2)
    conflict_citation_ids: list[CitationId] = Field(default_factory=list, max_length=8)
    clarification_question: SuggestionText | None = None
    feedback: Annotated[str, StringConstraints(max_length=500)] = ""
    suggestions_safe: bool = False


class SelfCheckVerdict(BaseModel):
    grounded: bool
    feedback: Annotated[str, StringConstraints(max_length=500)] = ""
    unsupported_claims: list[SuggestionText] = Field(default_factory=list, max_length=5)
    missing_information: list[SuggestionText] = Field(default_factory=list, max_length=6)
    recovery: str = "none"
    missing_requirement_ids: list[str] = Field(default_factory=list)
    answered_requirement_ids: list[str] = Field(default_factory=list)
    suggestions_safe: bool = False

    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def _adapt_verdict(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "claim_verdicts" in data and "grounded" not in data:
                verdicts = data.get("claim_verdicts", [])
                recovery = str(data.get("recovery", "none"))
                all_supported = bool(verdicts) and all(v.get("status") == "supported" for v in verdicts)
                if recovery == "regenerate":
                    all_supported = False
                missing = [str(r) for r in data.get("missing_requirement_ids", [])]
                safe = bool(data.get("suggestions_safe", False))
                answered = [str(r) for r in data.get("answered_requirement_ids", [])]
                return {
                    "grounded": all_supported,
                    "feedback": "Phát hiện phát biểu không được hỗ trợ" if not all_supported else "",
                    "unsupported_claims": ["unsupported claim"] if not all_supported else [],
                    "missing_information": missing[:3],
                    "missing_requirement_ids": missing,
                    "answered_requirement_ids": answered,
                    "recovery": recovery,
                    "suggestions_safe": safe,
                }
        return data

    @model_validator(mode="after")
    def _validate_disjoint(self) -> "SelfCheckVerdict":
        if self.grounded and self.unsupported_claims:
            raise ValueError("grounded=True cannot have unsupported_claims")
        if set(self.answered_requirement_ids) & set(self.missing_requirement_ids):
            self.answered_requirement_ids = [
                r for r in self.answered_requirement_ids if r not in self.missing_requirement_ids
            ]
        return self


class VerifiedAnswerSnapshot(BaseModel):
    """Immutable snapshot of an answer verified by check_grounding."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    answer: AnswerText
    draft_hash: str
    context_hash: str
    requirements_hash: str
    resolved_date: str
    corpus_fingerprint: str = ""
    citations: list[Citation] = Field(default_factory=list)
    answered_requirement_ids: list[str] = Field(default_factory=list)
    missing_requirement_ids: list[str] = Field(default_factory=list)
    missing_information: list[SuggestionText] = Field(default_factory=list)
    status: Literal["answered", "partial"]
    reason_code: ReasonCode | None = None
    created_at_attempt: int = 0
    answer_kind: Literal["factual", "mixed", "coaching"] = "factual"
    suggested_message: SuggestionText | None = None
    suggested_next_question: SuggestionText | None = None

    @model_validator(mode="after")
    def _validate_snapshot_invariants(self) -> "VerifiedAnswerSnapshot":
        if self.status == "partial" and not self.missing_information:
            raise ValueError("partial snapshot requires non-empty missing_information")
        if self.status == "answered" and self.missing_information:
            raise ValueError("answered snapshot cannot contain missing_information")
        return self


# Verbatim excerpt contracts remain available for source utilities, not the graph.
class EvidenceFinding(VerbatimQuote):
    requirement_id: RequirementId
    assessment: SuggestionText


CopilotRoute = Literal[
    "plan_queries",
    "retrieve_documents",
    "select_evidence",
    "build_context",
    "generate_answer",
    "check_grounding",
    "finalize_response",
    "fallback_response",
    "end",
]

ProfileName = Literal["simple", "complex", "corrective"]
RetrievalMode = Literal["search", "read_context"]


class CopilotState(TypedDict, total=False):
    verified_snapshot: VerifiedAnswerSnapshot | None
    evidence_map: dict[str, list[str]]
    recovery_requirement_ids: list[str]
    overflow_anchor_ids: list[str]
    evidence_selection_diagnostics: list[dict[str, Any]]
    selected_anchor_ids: list[str]
    evidence_query_provenance: dict[str, list[int]]
    evidence_query_references: dict[str, list[str]]
    rejected_evidence_ids: list[str]
    query: str
    target_date: date | str | None
    resolved_date: str
    customer_context: str
    memory_summary: str | None
    product_models: list[str]
    domain: str
    history: list[dict[str, str]]
    task: str
    answer_kind: Literal["factual", "mixed", "coaching"]
    analysis: IntakeDecision
    requirements: list[Requirement]
    search_plan: SearchPlan
    route: CopilotRoute
    retrieval_mode: RetrievalMode
    profile_name: ProfileName
    raw_search_results: list[dict[str, Any]]
    new_hits: list[RetrievalHit]
    candidate_evidence: list[RetrievalHit]
    evidence_registry: list[RetrievalHit]
    selected_evidence: list[RetrievalHit]
    answer_context: str
    draft_answer: str | None
    self_check: SelfCheckVerdict | None
    unsupported_claims: list[str]
    feedback: str
    read_anchor_ids: list[str]
    generation_count: int
    corrective_retrieval_count: int
    retrieval_rounds: int
    tool_calls: int
    parent_context_cache: dict[Any, Any]
    search_signatures: list[str]
    retrieval_errors: int
    clarification_question: str | None
    fallback_reason: ReasonCode
    final_response: CopilotResponse
    runtime: Any
    snapshot: Any
    readiness_loader: Any
    request_id: str
    trace: list[dict[str, Any]]
    progress_queue: Any
