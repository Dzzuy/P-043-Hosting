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

Compare saved predictions offline, including repeated judge runs over the same
transcripts:

```bash
PYTHONPATH=. .venv/bin/python -m eval.judge_eval.run --mode compare --predictions run-1.json run-2.json run-3.json
```

One prediction file retains the existing comparison report. Multiple files return
`runs` (the individual comparison reports in argument order), `mean_metrics`
(the mean of each numeric leaf in `metrics`, including per-criterion metrics),
and `stability`. Undefined metrics are excluded from their mean; a mean with no
defined values is null.

Stability uses only expert-approved labels, including approved unassessed labels.
`labels_compared` counts labels with valid predictions in every run.
`identical_across_runs` contains `count` and `rate` for matching status and score
in every run; `status_flip_count` counts labels switching assessed/unassessed.
`mean_score_range` averages max-minus-min scores for labels assessed in every
run. Rates and score ranges are null when their denominator is zero.
`per_label` lists each approved `(case_id, criterion)` with ordered predictions
(`run_index` is zero-based). Missing or invalid predictions have null status and
score and are excluded from stability denominators, never treated as unassessed.
Invalid cases appear in the affected run's `validation_errors`, with the case ID,
prediction index, and reason; other valid cases are still compared. Duplicate
case IDs invalidate that case for the run. File-level JSON/envelope errors remain
command errors.

## v4 calibration (`judge_calibration_v4.json`)

Rubric `sales-rubric-v4` labels for the same six cases. Run the adapter three
times (live model, one output per run), then compare:

```bash
PYTHONPATH=. .venv/bin/python -m eval.judge_eval.adapter --dataset eval/datasets/judge_calibration_v4.json --output run-1.json
# repeat for run-2.json and run-3.json
PYTHONPATH=. .venv/bin/python -m eval.judge_eval.run --mode compare --dataset eval/datasets/judge_calibration_v4.json --predictions run-1.json run-2.json run-3.json
```

Results for DeepSeek V3.2 (2026-10-18) are in
[`eval/reports/judge_calibration_v4_compare_2026-10-18.md`](../reports/judge_calibration_v4_compare_2026-10-18.md).

Limitations:

- JC6 failed in all three runs (structured output failure or inexact factual
  source quote), so only JC1-JC5 are evaluated.
- Applicability agreement is 76% (19/25). Unassessed is a valid label by design
  (no fair opportunity, no score); five disagreeing cells await re-check by the
  sales expert Tú.
