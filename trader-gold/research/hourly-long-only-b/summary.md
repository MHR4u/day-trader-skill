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
- Resolved config SHA-256: `2645bdb4fc258cbaf5eafb0a24e3e4369331c00457a69668a4dc4a54511c331a`

## Validation summary

```json
{
  "folds": 19,
  "oos_expectancy_r": 0.025786,
  "oos_net_profit": 578.77,
  "oos_profit_factor": 1.053854,
  "oos_trades": 1124,
  "positive_fold_ratio": 0.631579,
  "positive_folds": 12,
  "positive_year_profit_concentration_pct": 19.319788,
  "stress_net_profit": -486.01,
  "worst_fold_max_drawdown_pct": 3.743588,
  "worst_fold_stress_profit_factor": 0.157959,
  "yearly_oos_net_profit": {
    "2007": 253.56,
    "2008": -235.2,
    "2009": 12.01,
    "2010": -252.7,
    "2011": 15.63,
    "2012": -59.08,
    "2013": -283.5,
    "2014": -101.94,
    "2015": 88.61,
    "2016": 257.13,
    "2017": 198.7,
    "2018": -273.69,
    "2019": 113.65,
    "2020": 359.21,
    "2021": -74.4,
    "2022": 23.86,
    "2023": 65.96,
    "2024": 113.95,
    "2025": 357.01
  }
}
```

## Gates

- enough_folds: PASS
- enough_oos_trades: PASS
- oos_profit_factor: FAIL
- positive_fold_ratio: PASS
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
