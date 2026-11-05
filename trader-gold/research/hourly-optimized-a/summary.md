# Gold EA research result

Status: **RESEARCH_ONLY**
Deployment: **MT5_VALIDATION_REQUIRED**

This is an automated research result, not financial advice or a promise of profit.

## Evidence

- Mode: walk-forward
- Data rows: 122028
- Data coverage: 2004-06-11T07:00:00Z to 2025-06-06T07:00:00Z
- Data SHA-256: `3b94158402f3628e7b2c4a9fb1f37bca412a3116d279303b788a149e0782ef7b`
- Method: Rolling fixed-length walk-forward; parameters selected on training only, then tested once on the next unseen window
- Equity file: concatenated per-fold OOS equity; each fold restarts from the configured initial balance
- Resolved config SHA-256: `85aaf2dd2eac791df91a3f4f899766d215784147db97081514c4ed1454bc9ef7`

## Validation summary

```json
{
  "folds": 19,
  "oos_expectancy_r": -0.01299,
  "oos_net_profit": -812.92,
  "oos_profit_factor": 0.971446,
  "oos_trades": 2645,
  "positive_fold_ratio": 0.368421,
  "positive_folds": 7,
  "positive_year_profit_concentration_pct": 25.678231,
  "stress_net_profit": -3261.17,
  "worst_fold_max_drawdown_pct": 6.71723,
  "worst_fold_stress_profit_factor": 0.631312,
  "yearly_oos_net_profit": {
    "2007": -258.97,
    "2008": 193.37,
    "2009": -138.84,
    "2010": -660.77,
    "2011": 451.36,
    "2012": 45.6,
    "2013": -118.82,
    "2014": 160.35,
    "2015": -39.11,
    "2016": -229.21,
    "2017": 475.96,
    "2018": -234.73,
    "2019": -27.97,
    "2020": 175.7,
    "2021": -246.3,
    "2022": -152.91,
    "2023": -469.4,
    "2024": -89.45,
    "2025": 351.22
  }
}
```

## Gates

- enough_folds: PASS
- enough_oos_trades: PASS
- oos_profit_factor: FAIL
- positive_fold_ratio: FAIL
- drawdown: PASS
- positive_stress_net: FAIL
- stress_profit_factor: FAIL
- profit_concentration: PASS
- data_coverage: FAIL
- ea_static_review: PASS
- mt5_compile_and_real_tick_test: FAIL
- demo_forward_test: FAIL
- data_coverage: FAIL
- mt5_compile_and_real_tick_test: NOT RUN
- demo_forward_test: NOT RUN

## Required next step

Use broker-specific XAUUSD data, compile the EA in MetaEditor, then run MT5 Every tick based on real ticks with variable spread. Keep new entries disabled until independent out-of-sample and demo forward tests are acceptable.

The Python engine uses bars and a stop-first ambiguity rule. Its results can differ from MT5 tick execution, swaps, broker contract size, news blackout behavior and actual slippage.
