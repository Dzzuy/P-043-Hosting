# Roleplay multilingual injection hardening — 2026-10-13

## Scope

Seven isolated advisor-message probes used Vietnamese, English, Chinese, Spanish, and mixed-language instructions to disclose private context, impersonate a system/tool message, or make the AI customer act as an evaluator. The scenario and canary were synthetic. No hosted API, real customer session, or production data was used. Raw model replies before and after the code change are in `roleplay_multilingual_injection_2026-10-13.json`.

## Observations

- All seven probes executed in each phase. None returned the exact canary. On manual inspection, all published replies were in Vietnamese and stayed in a buyer's voice.
- These model samples did not demonstrate a successful attack before the change. Differences between the two runs cannot be attributed to hardening alone because generation is nondeterministic.
- Deterministic tests forced the model boundary to output private persona data, a long verbatim system-prompt excerpt, Chinese, and Spanish. The application now rejects those outputs before they become customer messages, with one bounded correction attempt. The correction prompt does not repeat protected data.

## Code behavior and limits

The system prompt now states that the trust boundary applies across languages and forged system/tool formats. The output gate checks exact private persona values carried in keys such as `private` or `control`, substantial verbatim system-prompt excerpts, and selected foreign-language prose/scripts. Normal Vietnamese replies do not incur another model call; unsafe replies may incur one retry. A local microbenchmark measured about 0.7 ms for the prompt-excerpt check on a normal long reply; this is not a production latency measurement.

Rejected outputs are logged with session ID and rejection reason, without logging the rejected reply or private value.

This does **not** detect every language, paraphrased disclosure, or semantic role reversal in Vietnamese. The advisor-turn analyzer and evaluator were not changed in this patch. Their model-generated decisions still need adversarial testing. The hosted website remains unverified until the branch completes review, CI, release, and production smoke checks.
