"""Bind model judgments to actual claims, requirements and selected source IDs."""

import re

from src.agents.copilot.state import SelfCheckVerdict


def _quote_exists(quote, source):
    return any(
        " ".join(quote.split()) in " ".join((source.get(key) or "").split())
        for key in ("content", "title", "section", "context_prefix")
    )


def bind_citation_dependencies(answer, state):
    """Canonicalize display markers and attach selected source dependencies.

    This supplies no new facts and never searches outside selected evidence.
    The checker still has to judge the resulting claim against these citations.
    """
    sources = {h["chunk_id"]: h["citation_id"] for h in state.get("selected_evidence", [])}
    dependencies = {
        sources[d["chunk_id"]]: [sources[cid] for cid in d["bundle_chunk_ids"] if cid in sources]
        for d in state.get("evidence_selection_diagnostics", [])
        if d["reason"] == "selected" and d["chunk_id"] in sources
    }
    for claim in answer.claims:
        # Strip only redundant display markers already declared on this block.
        # Unknown/malformed markers remain for validation to reject. This changes
        # presentation only; facts and citation links still go to the checker.
        claim.text = re.sub(
            r"\[\s*([cC][1-9]\d*)\s*\]",
            lambda match: "" if match.group(1).upper() in claim.citation_ids else match.group(0),
            claim.text,
        ).strip()
        if not claim.text:
            raise ValueError("claim has no text after display marker removal")
        # Dependencies can themselves be retrieved anchors. Close the selected
        # dependency graph, bounded by the source registry, without truncation.
        citation_ids = list(claim.citation_ids)
        for cid in citation_ids:
            citation_ids.extend(dep for dep in dependencies.get(cid, []) if dep not in citation_ids)
        claim.citation_ids = citation_ids


def validate_generated_answer(answer, state):
    requirements = {r.requirement_id: r for r in state.get("requirements", [])}
    sources = {h["citation_id"] for h in state.get("selected_evidence", [])}
    for claim in answer.claims:
        if not set(claim.requirement_ids) <= requirements.keys():
            raise ValueError("unknown requirement in generated answer")
        if not set(claim.citation_ids) <= sources:
            raise ValueError("citation outside selected evidence")
        if re.search(r"\[\s*[cC][^\]]*\]", claim.text):
            raise ValueError("citation markers must be rendered from citation_ids")
        if claim.kind == "fact" and not any(requirements[rid].kind == "fact" for rid in claim.requirement_ids):
            raise ValueError("factual claim without factual requirement")
        if claim.kind == "fact":
            cited_sources = [h for h in state.get("selected_evidence", []) if h["citation_id"] in claim.citation_ids]
            for rid in claim.requirement_ids:
                model = requirements[rid].product_model
                if model and model != "ALL" and not any(h["product_model"] in {model, "ALL"} for h in cited_sources):
                    raise ValueError("cited sources outside requirement model")
    if len(render_answer(answer)) > 12000:
        raise ValueError("rendered answer exceeds public limit")


def render_answer(answer):
    """Render only validated blocks, including citations inside the last table cell."""
    blocks = []
    for claim in answer.claims:
        text = claim.text.rstrip()
        markers = "".join(f"[{cid}]" for cid in claim.citation_ids)
        if markers:
            if text.splitlines()[-1].strip().startswith("|") and text.endswith("|"):
                text = text[:-1].rstrip() + " " + markers + " |"
            else:
                text += " " + markers
        blocks.append(text)
    return "\n\n".join(blocks)


def validate_grounding_review(review, state):
    claims = state["generated_answer"].claims
    sources = {h["citation_id"]: h for h in state.get("selected_evidence", [])}
    indices = [v.claim_index for v in review.claim_verdicts]
    if len(set(indices)) != len(indices) or set(indices) != set(range(len(claims))):
        raise ValueError("checker must evaluate every claim exactly once")
    for verdict in review.claim_verdicts:
        if verdict.status == "supported" and verdict.error_codes:
            raise ValueError("supported claim cannot carry verification errors")
        claim = claims[verdict.claim_index]
        for proof in verdict.evidence_proofs:
            if proof.citation_id not in claim.citation_ids or proof.citation_id not in sources:
                raise ValueError("evidence proof outside claim citations")
            source = sources[proof.citation_id]
            # A quote must come from actual selected content/headers, not a document ID
            # or a concatenation that invents a relationship between unrelated fields.
            if not _quote_exists(proof.quote, source):
                raise ValueError("evidence quote not found in cited source")
    requirements = {r.requirement_id: r for r in state.get("requirements", [])}
    ids = [v.requirement_id for v in review.requirement_verdicts]
    if len(set(ids)) != len(ids) or set(ids) != set(requirements):
        raise ValueError("checker must evaluate every requirement exactly once")
    for verdict in review.requirement_verdicts:
        evidence_ids = verdict.evidence_citation_ids
        if len(set(evidence_ids)) != len(evidence_ids) or not set(evidence_ids) <= sources.keys():
            raise ValueError("diagnostic citation outside selected evidence")
        requirement = requirements[verdict.requirement_id]
        for proof in verdict.evidence_proofs:
            if proof.citation_id not in evidence_ids:
                raise ValueError("evidence proof outside diagnostic citations")
            if not _quote_exists(proof.quote, sources[proof.citation_id]):
                raise ValueError("evidence quote not found in cited source")
        if verdict.evidence_status == "sufficient" and requirement.kind == "fact":
            if not evidence_ids:
                raise ValueError("sufficient evidence requires source citations")
            if requirement.product_model and requirement.product_model != "ALL" and not any(
                sources[cid]["product_model"] in {requirement.product_model, "ALL"} for cid in evidence_ids
            ):
                raise ValueError("diagnostic sources outside requirement model")
        if requirement.kind == "external" and verdict.evidence_status == "sufficient":
            raise ValueError("external evidence cannot be established from corpus")
        if verdict.evidence_status == "sufficient" and verdict.blocker in {"missing_input", "external_data", "source_conflict"}:
            raise ValueError("unresolved evidence blocker cannot have sufficient context")
        if verdict.status == "answered" and verdict.blocker != "none":
            raise ValueError("answered requirement cannot have a blocker")
        if verdict.status == "answered" and verdict.evidence_status in {"partial", "not_found"}:
            raise ValueError("answered requirement cannot have incomplete evidence")
        linked = verdict.supporting_claim_indices
        if len(set(linked)) != len(linked) or not set(linked) <= set(indices):
            raise ValueError("invalid supporting claim indices")
        if verdict.status == "missing":
            if linked:
                raise ValueError("missing requirement cannot have supporting claims")
            continue
        if not linked or verdict.missing_information:
            raise ValueError("answered requirement requires support and no missing information")
        requirement = requirements[verdict.requirement_id]
        if requirement.kind == "external":
            raise ValueError("external requirement cannot be verified from the corpus")
    answered = {v.requirement_id for v in review.requirement_verdicts if v.status == "answered"}
    for rid in answered:
        if not set(requirements[rid].depends_on) <= answered:
            raise ValueError("derived requirement has unverified inputs")


def summarize_grounding_review(review, state):
    """Derive approval and missing requirements; never accept a model-wide grounded flag."""
    validate_grounding_review(review, state)
    claims = state["generated_answer"].claims
    reqs = {r.requirement_id: r for r in state.get("requirements", [])}
    effective = []
    proof_failures = {
        v.requirement_id for v in review.requirement_verdicts
        if reqs[v.requirement_id].kind == "fact"
        and (v.evidence_status == "sufficient" or v.status == "answered")
        and (v.evidence_status != "sufficient" or not v.evidence_proofs)
    }
    for original in review.claim_verdicts:
        item = original.model_copy(deep=True)
        if item.status == "supported" and claims[item.claim_index].kind == "fact" and not item.evidence_proofs:
            item.status = "unsupported"
            item.error_codes = ["missing_evidence"]
            item.feedback = "Checker chưa trích chứng cứ nguồn cho phát biểu thực tế; kiểm tra lại số liệu, phạm vi và điều kiện."
        effective.append(item)
    unsupported = [v for v in effective if v.status != "supported"]
    claim_verdicts = {v.claim_index: v for v in effective}
    answered, missing = [], []
    for verdict in review.requirement_verdicts:
        # A checker may call a goal answered while linking an unrelated or
        # unsupported block. Downgrade this goal instead of discarding all valid
        # judgments. Unknown indices/IDs still fail structural validation above.
        supported = verdict.status == "answered" and verdict.requirement_id not in proof_failures and all(
            claim_verdicts[index].status == "supported"
            and verdict.requirement_id in claims[index].requirement_ids
            and claims[index].kind != "limitation"
            and (reqs[verdict.requirement_id].kind != "fact" or claims[index].kind == "fact")
            for index in verdict.supporting_claim_indices
        )
        (answered if supported else missing).append(verdict)
    dependency_failure = False
    while True:
        answered_ids = {v.requirement_id for v in answered}
        invalid = [v for v in answered if not set(reqs[v.requirement_id].depends_on) <= answered_ids]
        if not invalid:
            break
        dependency_failure = True
        missing.extend(invalid)
        answered = [v for v in answered if v not in invalid]
    feedback = "\n".join(filter(None, [review.feedback, *[v.feedback for v in unsupported]]))[:500]
    answered_ids = {v.requirement_id for v in answered}
    diagnostics = []
    for original in review.requirement_verdicts:
        item = original.model_copy(deep=True)
        # A wrong draft can coexist with incomplete sources. Preserve both axes:
        # claim verdicts describe the answer error; recovery follows the source
        # gap instead of rejecting every valid judgment over one blocker label.
        if item.blocker in {"answer_omission", "incorrect_answer"} and item.evidence_status != "sufficient":
            item.blocker = "verification_uncertain" if item.evidence_status == "unknown" else "insufficient_context"
        if item.requirement_id not in answered_ids:
            item.status = "missing"
            item.supporting_claim_indices = []
            if item.requirement_id in proof_failures:
                item.evidence_status = "unknown"
                item.blocker = "verification_uncertain"
                item.missing_information = ("Checker chưa cung cấp chứng cứ cho: "
                                            + reqs[item.requirement_id].description)[:500]
            elif item.evidence_status == "sufficient":
                if original.status == "answered" or item.blocker == "none":
                    item.blocker = "incorrect_answer" if any(
                        v.status != "supported" and item.requirement_id in claims[v.claim_index].requirement_ids
                        for v in effective
                    ) else "answer_omission"
                    item.missing_information = ("Chưa hoàn tất câu trả lời dù ngữ cảnh đã có nguồn cho: "
                                                + reqs[item.requirement_id].description)[:500]
            else:
                item.missing_information = item.missing_information or reqs[item.requirement_id].description
                if item.blocker == "none":
                    item.blocker = "verification_uncertain"
        diagnostics.append(item)
    return SelfCheckVerdict(
        grounded=not unsupported and review.suggestions_safe and not dependency_failure,
        supported_claim_indices=[v.claim_index for v in effective if v.status == "supported"],
        feedback=feedback,
        unsupported_claims=[claims[v.claim_index].text[:500] for v in unsupported][:5],
        missing_information=[v.missing_information for v in diagnostics if v.status == "missing"],
        answered_requirement_ids=[v.requirement_id for v in answered],
        missing_requirement_ids=[v.requirement_id for v in missing],
        requirement_diagnostics=diagnostics,
        recovery="regenerate" if proof_failures or missing and not any(v.status == "missing" for v in missing) else review.recovery,
    )


def verified_answer(review, state):
    """Retain supported blocks and honestly report goals that remain unproven.

    Preserve the original draft/review in state. Never salvage unsafe text, an
    unproven goal or a derived claim whose dependencies failed verification.
    """
    verdict = summarize_grounding_review(review, state)
    generated = state["generated_answer"]
    if verdict.grounded:
        return generated, verdict
    if not review.suggestions_safe or not verdict.answered_requirement_ids or not verdict.supported_claim_indices:
        return None, verdict
    indices = verdict.supported_claim_indices
    remap = {old: new for new, old in enumerate(indices)}
    projected = generated.model_copy(deep=True)
    projected.claims = [projected.claims[i] for i in indices]
    projected_review = review.model_copy(deep=True)
    projected_review.requirement_verdicts = [d.model_copy(deep=True) for d in verdict.requirement_diagnostics]
    projected_review.claim_verdicts = [v for v in projected_review.claim_verdicts if v.claim_index in remap]
    for item in projected_review.claim_verdicts:
        item.claim_index = remap[item.claim_index]
    for item in projected_review.requirement_verdicts:
        item.supporting_claim_indices = [remap[i] for i in item.supporting_claim_indices]
    projected_verdict = summarize_grounding_review(projected_review, {**state, "generated_answer": projected})
    # Projection is a publication decision, not a repair of the original draft.
    # Keep the removed blocks' feedback so another generation can explain gaps
    # rather than silently losing why those facts were rejected.
    projected_verdict.feedback = verdict.feedback
    projected_verdict.unsupported_claims = verdict.unsupported_claims
    projected_verdict.recovery = verdict.recovery
    return (projected, projected_verdict) if projected_verdict.grounded else (None, verdict)
