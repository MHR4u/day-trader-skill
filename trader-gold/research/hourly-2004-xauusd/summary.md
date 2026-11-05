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
- Resolved config SHA-256: `4ac48bf286ccd576144575c02a951167cad83524b825489073ccacf1cee7c12b`

## Validation summary

```json
{
  "folds": 19,
  "oos_expectancy_r": -0.004201,
  "oos_net_profit": -239.74,
  "oos_profit_factor": 0.989344,
  "oos_trades": 2226,
  "positive_fold_ratio": 0.526316,
  "positive_folds": 10,
  "positive_year_profit_concentration_pct": 19.42503,
  "stress_net_profit": -1955.69,
  "worst_fold_max_drawdown_pct": 4.937704,
  "worst_fold_stress_profit_factor": 0.628025,
  "yearly_oos_net_profit": {
    "2007": -176.09,
    "2008": 271.01,
    "2009": 266.42,
    "2010": -360.12,
    "2011": 356.84,
    "2012": 55.31,
    "2013": -219.99,
    "2014": 14.66,
    "2015": 162.53,
    "2016": -174.17,
    "2017": 367.38,
    "2018": -318.47,
    "2019": -463.96,
    "2020": 4.53,
    "2021": -266.63,
    "2022": -63.95,
    "2023": -87.62,
    "2024": 133.92,
    "2025": 258.64
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
