# Judge calibration

`judge_calibration.json` contains six expert-approved cases, including
`JC6_VF6_PLUS_UPSELL`, the scenario-04 VF 6 Plus upsell conversation. JC6 scores
were AI-drafted, then human-reviewed and approved by Tú, a VinFast sales advisor, on
2026-10-17. Validation reports `READY_FOR_COMPARISON`, with 30 approved labels
and no missing expert labels. The original JC1–JC5 case bytes and dataset
version are preserved; JC6 does not relabel or supersede their v1 annotations.

For a criterion awaiting review, the pending-label contract uses `review_status: PENDING_EXPERT_REVIEW`,
`adjudication_status: PENDING`, null status/score/review provenance, and empty
evidence. Validation reports pending expert review; comparison excludes these
labels from every agreement denominator even if an AI prediction is present.
AI predictions never promote pending labels to approved labels.

Offline validation and comparison retain the stored rubric and scenario
versions. The original cases use historical scenario versions and rubric v3,
while the current evaluator uses v4; reports expose this drift. The adapter
requires matching scenario versions to prepare evaluator state and matching
rubric versions before calling a live model. New expert review or a deliberate
versioned calibration migration is required before evaluating with rubric v4.
Knowledge evidence is loaded from both `data/knowledge/corpus.json` and
`data/knowledge/faq.json`, with source version and exact quote checks.

```bash
APP_ENV=test .venv/bin/python -m eval.judge_eval.run
APP_ENV=test .venv/bin/python -m eval.judge_eval.adapter --preflight --case-id JC6_VF6_PLUS_UPSELL
```

The second command validates the approved JC6 case without constructing an LLM and
reports `OFFLINE_VALIDATED_RUBRIC_MISMATCH`; this is not approval to run a live
evaluation. `run --mode live` remains a dry path with exit code 3 and no model
calls.
