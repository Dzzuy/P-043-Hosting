# Role-play runtime contracts

Scenario JSON is the source of product outcomes, objections, upsell benefits and
policy expectations. The analyzer extracts signals; the reducer validates IDs,
accumulates unique benefit/need pairs and policy IDs, and applies transitions.
`visible_goals` represents needs stated in `customer_goals`; other benefit links
must reference a fact key already revealed before that advisor turn. A feature
list alone is not a linked benefit: the analyzer must identify an explicit link
in the advisor's message to the customer's need.

SCENARIO_04 version 1.4 keeps daily family usage, weekend trips and buying
priorities private until the advisor asks a relevant discovery question. The
first customer reply introduces interest in VF 6 Eco and may ask about the
promotion; it does not volunteer usage needs. Its Plus benefits all require
configured discovered facts, including `family_usage` for the seven airbags;
none receives credit through `visible_goals`.

Objections activate on their stage or a case-insensitive whole-word keyword.
An upsell objection can resolve only after the configured number of distinct
linked benefits and safety benefits has accumulated. Neither analyzer resolution
signals nor customer acceptance can bypass this rule. Objections can declare
`requires_revealed_facts`, validated against `hidden_facts`; resolution requires
those facts to be revealed before the advisor turn. Scenario 04 promotion
eligibility requires `current_vehicle`; a bare confirmation before discovery
cannot resolve it.

Analysis failures happen before advisor-turn persistence and return HTTP 503
`message_not_sent` (resend the message). Customer-generation failures happen after
persistence and return `provider_unavailable` (retry the pending customer reply).
Session conflicts use explicit exception codes. Assignment and review conflicts
return `assignment_conflict` and `review_conflict` with localized reasons.

Customer acceptance records `closing_outcome` only for a concrete proposed next
step. Outcomes must exist and have all prerequisite objections resolved. Invalid
or ineligible selections fall back to a preferred outcome without prerequisites,
then another outcome without prerequisites, or null. Legacy scenarios retain the
`close` outcome. Acceptance keeps the conversation available until the advisor
finishes it, matching the existing practice flow.

Disclosures stay deterministic: a pending fact is spoken through its
configured revealed statement, and the graph records it by exact match. Customer
output is retried once when it introduces a price or numeric specification not
already present in advisor dialogue, a revealed statement, the visible scenario
context or an active objection's text. Ordinary model names
and appointment times are allowed. This guard is deterministic pattern checking;
semantic role compliance remains part of the customer prompt.

Advisor abuse is screened locally before the analyzer provider call. The local
registry uses word boundaries, Unicode normalization and conservative accent
folding to preserve normal sales phrases. Mild slang returns a warning verdict;
explicit abuse ends the session. The analyzer's semantic `unsafe_or_abusive`
signal independently ends the session. Both paths persist `advisor_misconduct`,
a category-only reason, the finished stage, and one scripted customer reply
without customer generation. Local guardrail abuse uses a report-to-manager exit;
analyzer-only abuse keeps the neutral goodbye. New messages receive HTTP 409.
Finish and evaluation use the normal terminated-session lifecycle. The frontend keeps the score button
and displays the misconduct banner.

The analyzer's `off_topic` signal increments `consecutive_off_topic_turns`; a
relevant turn resets it. After one off-topic turn, the customer context sets
`advisor_off_topic` so the customer can ask for clarification and return to the
buying need. Two consecutive off-topic turns end the session as `dropped_out`
with a scripted goodbye and no customer model call. Termination precedence is
misconduct, explicit advisor finish, repeated off-topic messages, then the turn
limit. The customer prompt never permits the model to announce ending a session.

The public session view includes `closing_outcome` and `termination_reason`,
without private customer state. The scorecard renders `closing_outcome_label`
when supplied by evaluation. The catalog loads `/practice/scenarios`; static
presets are not its source. VF 6 retains its existing backend scenario 03 link.

Deterministic specs: `tests/test_roleplay/test_scenario04_runtime.py`, including
all 25 positive and 25 negative cases from the supplied abuse-pattern catalog.

## Verification on 2026-10-16

- 255 passed: `APP_ENV=test env -u OPENROUTER_API_KEY -u LLM_PROVIDER .venv/bin/python -m pytest tests/test_roleplay tests/test_api/test_practice_chat.py tests/test_api/test_recorded_practice.py tests/test_integrations/test_practice_runtime.py tests/test_integrations/test_practice_composition.py tests/test_integrations/test_practice_records.py tests/test_integrations/test_practice_persistence.py tests/test_integrations/test_practice_knowledge.py -q`.
- The new runtime spec file contributes 81 passing cases. Evaluation persistence
  after misconduct is verified using deterministic evaluator and evidence fakes.
- Ruff check and format check passed on all 11 changed Python files.
- Frontend production build and ESLint on both changed role-play components passed.
- Full frontend lint fails in untouched `components/copilot/SourceViewerModal.jsx:15`
  (`react-hooks/set-state-in-effect`); Copilot edits are outside this task's scope.
- The requested full backend command was attempted and interrupted after stalling
  on `test_copilot_agentic::test_simple_graph_has_nine_nodes_and_three_calls`.
  Diagnostic tracebacks showed the event loop waiting and an idle executor worker;
  an isolated `asyncio.to_thread` probe also stalled in this sandbox. Full-suite
  status is not verified, including the coordinator's known observability failure.
- No live provider evaluation, deployment, GitHub CI, or mergeability checks ran.
  No commit or push was made; generated tracked build output was restored.


Policy validity uses the session creation date in Vietnam time. Split retrieval
chunks inherit programme windows from the full corpus document by source offset
or section path. Legacy checkpoints use the recorded attempt's `started_at` during
evaluation; sessions with neither timestamp use today's Vietnam date and log a
warning containing the session ID.
