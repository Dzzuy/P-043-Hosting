# Roleplay evaluation

The Gate 4 runner remains `python -m eval.roleplay_eval.run`.
The multi-scenario runner is `python -m eval.roleplay_eval.golden`.

```bash
# Offline validation of the entire dataset (default mode).
APP_ENV=test python -m eval.roleplay_eval.golden --mode validate

# Live calls cost money. Only APPROVED cases run by default.
python -m eval.roleplay_eval.golden --mode live --repeats 3 --output report.json

# Optional filters; each filter can be repeated.
python -m eval.roleplay_eval.golden --mode live --include-draft \
  --case-id S01_ON_DISCOVERY_WORK_SCHEDULE \
  --scenario-id SCENARIO_01_VF5_TAXI --type on_topic \
  --repeats 3 --output draft-report.json
```

Every repetition uses a fresh session and an isolated in-memory checkpoint.
Terminal sessions stop receiving messages; final assertions still run, while
checkpoints that were never reached remain NOT_EVALUATED. Factual checks reuse
the Gate 4 evaluator and provenance checks. Spoken-message links verify structure,
not the independent semantic correctness of the customer response.

The JSON report includes individual runs and assertions, per-case pass counts,
pass@k (at least one passing run), and pass^k (every run passes). These are
empirical repeated-run metrics, not statistical estimators.
Approved metrics and draft metrics are separate, grouped overall, by type,
and by scenario. Rejected cases never run. Assertion pass rate counts all
assertions, including unavailable assertions in the denominator. Empty rates
are null. Validation reports contain no behavioral metrics.

An explicit output must end in .json; a Markdown summary is written alongside
it with the same stem. Existing JSON or Markdown outputs are refused before
execution. Exit codes: 0 for valid datasets or all selected live cases passing
every repetition; 1 for empty live selection or non-passing live results;
2 for invalid datasets, arguments, or output errors.
