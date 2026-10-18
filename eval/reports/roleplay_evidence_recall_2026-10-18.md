# Roleplay evidence recall

Mode: run

| Group | Passing / cells | Recall | Mean evidence chunks |
|---|---:|---:|---:|
| overall | 107 / 147 | 72.8% | 3.79 |
| by_category/product | 14 / 21 | 66.7% | 3.71 |
| by_category/price | 17 / 21 | 81.0% | 4.14 |
| by_category/promotion | 17 / 21 | 81.0% | 5.67 |
| by_category/policy | 15 / 21 | 71.4% | 3.33 |
| by_category/warranty | 13 / 21 | 61.9% | 3.00 |
| by_category/battery_charging | 16 / 21 | 76.2% | 3.33 |
| by_category/other | 15 / 21 | 71.4% | 3.33 |
| by_source/golden | 67 / 91 | 73.6% | 3.65 |
| by_source/paraphrase | 40 / 56 | 71.4% | 4.02 |
| by_probe/S01_ON_FACT_VF5_SUPPORTED#0 | 7 / 7 | 100.0% | 3.57 |
| by_probe/S01_ON_FACT_VF5_SUPPORTED#1 | 7 / 7 | 100.0% | 3.00 |
| by_probe/S01_EDGE_FALSE_RANGE#0 | 7 / 7 | 100.0% | 3.57 |
| by_probe/S02_ON_FACT_VF7_SUPPORTED#0 | 4 / 7 | 57.1% | 3.86 |
| by_probe/S02_ON_FACT_VF7_SUPPORTED#1 | 0 / 7 | 0.0% | 3.00 |
| by_probe/S02_EDGE_FALSE_WARRANTY#0 | 0 / 7 | 0.0% | 3.00 |
| by_probe/S03_ON_CHARGING_OBJECTION#0 | 7 / 7 | 100.0% | 3.86 |
| by_probe/S04_EDGE_FALSE_PROMO#0 | 6 / 7 | 85.7% | 4.71 |
| by_probe/S01_ON_FACT_FAST_CHARGE#0 | 7 / 7 | 100.0% | 3.57 |
| by_probe/S01_ON_FACT_VF5_BATTERY_CAPACITY#0 | 7 / 7 | 100.0% | 3.57 |
| by_probe/S02_ON_FACT_HOME_CHARGER_PRICE#0 | 3 / 7 | 42.9% | 4.00 |
| by_probe/S02_ON_FACT_VF7_AWD_RANGE#0 | 5 / 7 | 71.4% | 3.71 |
| by_probe/S03_ON_FACT_IDLE_FEE#0 | 7 / 7 | 100.0% | 4.00 |
| by_probe/TARIFF_PER_KWH_WORDS | 7 / 7 | 100.0% | 3.86 |
| by_probe/IDLE_FEE_PARAPHRASE | 7 / 7 | 100.0% | 3.86 |
| by_probe/BATTERY_CAPACITY_PARAPHRASE | 7 / 7 | 100.0% | 3.57 |
| by_probe/FAST_CHARGE_DC_POST | 7 / 7 | 100.0% | 5.57 |
| by_probe/MSRP_VF5 | 2 / 7 | 28.6% | 3.71 |
| by_probe/MSRP_VF6_ECO | 5 / 7 | 71.4% | 3.71 |
| by_probe/MIXED_PRICE_AND_RANGE | 2 / 7 | 28.6% | 3.71 |
| by_probe/HOME_CHARGER_PARAPHRASE | 3 / 7 | 42.9% | 4.14 |

## Probe × category

| Probe | product | price | promotion | policy | warranty | battery_charging | other |
|---|---|---|---|---|---|---|---|
| S01_ON_FACT_VF5_SUPPORTED#0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S01_ON_FACT_VF5_SUPPORTED#1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S01_EDGE_FALSE_RANGE#0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S02_ON_FACT_VF7_SUPPORTED#0 | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| S02_ON_FACT_VF7_SUPPORTED#1 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| S02_EDGE_FALSE_WARRANTY#0 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| S03_ON_CHARGING_OBJECTION#0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S04_EDGE_FALSE_PROMO#0 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ |
| S01_ON_FACT_FAST_CHARGE#0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S01_ON_FACT_VF5_BATTERY_CAPACITY#0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S02_ON_FACT_HOME_CHARGER_PRICE#0 | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ |
| S02_ON_FACT_VF7_AWD_RANGE#0 | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ |
| S03_ON_FACT_IDLE_FEE#0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| TARIFF_PER_KWH_WORDS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| IDLE_FEE_PARAPHRASE | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| BATTERY_CAPACITY_PARAPHRASE | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| FAST_CHARGE_DC_POST | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| MSRP_VF5 | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| MSRP_VF6_ECO | ✗ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ |
| MIXED_PRICE_AND_RANGE | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| HOME_CHARGER_PARAPHRASE | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ |
