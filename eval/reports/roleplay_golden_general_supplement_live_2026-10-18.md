# Roleplay golden evaluation

Mode: live; K: 1

Approved metrics exclude drafts. Unavailable assertions count as non-passing.

## metrics

| Group | Cases | pass@k | pass^k | Assertion pass rate |
|---|---:|---:|---:|---:|
| overall | 10 | 60.0% | 60.0% | 92.6% |
| by_type/edge | 3 | 66.7% | 66.7% | 95.2% |
| by_type/on_topic | 7 | 57.1% | 57.1% | 91.7% |
| by_scenario_id/SCENARIO_01_VF5_TAXI | 3 | 100.0% | 100.0% | 100.0% |
| by_scenario_id/SCENARIO_02_VF7_VS_CX5 | 4 | 25.0% | 25.0% | 87.1% |
| by_scenario_id/SCENARIO_03_VF6_APARTMENT | 2 | 50.0% | 50.0% | 89.5% |
| by_scenario_id/SCENARIO_04_VF6_ECO_PLUS_UPSELL | 1 | 100.0% | 100.0% | 100.0% |

## draft_metrics

| Group | Cases | pass@k | pass^k | Assertion pass rate |
|---|---:|---:|---:|---:|
| overall | 1 | 0.0% | 0.0% | 71.4% |
| by_type/on_topic | 1 | 0.0% | 0.0% | 71.4% |
| by_scenario_id/SCENARIO_01_VF5_TAXI | 1 | 0.0% | 0.0% | 71.4% |

## Cases

| Case | Review | Runs | Passes | pass@k | pass^k |
|---|---|---:|---:|---|---|
| S01_ON_FACT_VF5_SUPPORTED | APPROVED | 1 | 1 | True | True |
| S01_EDGE_FALSE_RANGE | APPROVED | 1 | 1 | True | True |
| S02_ON_FACT_VF7_SUPPORTED | APPROVED | 1 | 0 | False | False |
| S02_EDGE_FALSE_WARRANTY | APPROVED | 1 | 0 | False | False |
| S03_ON_CHARGING_OBJECTION | APPROVED | 1 | 1 | True | True |
| S04_EDGE_FALSE_PROMO | APPROVED | 1 | 1 | True | True |
| S01_ON_FACT_FAST_CHARGE | APPROVED | 1 | 1 | True | True |
| S01_ON_FACT_VF5_BATTERY_CAPACITY | PENDING_EXPERT_REVIEW | 1 | 0 | False | False |
| S02_ON_FACT_HOME_CHARGER_PRICE | APPROVED | 1 | 0 | False | False |
| S02_ON_FACT_VF7_AWD_RANGE | APPROVED | 1 | 1 | True | True |
| S03_ON_FACT_IDLE_FEE | APPROVED | 1 | 0 | False | False |

