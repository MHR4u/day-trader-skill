# Gold EA research result

Status: **RESEARCH_ONLY**
Deployment: **MT5_VALIDATION_REQUIRED**

This is an automated research result, not financial advice or a promise of profit.

## Evidence

- Mode: walk-forward
- Data rows: 5703
- Data coverage: 2000-01-04T00:00:00Z to 2022-09-03T00:00:00Z
- Data SHA-256: `2456f85acddedd11ec78c56c9bb500e9bb72bb5a2d415a1a0f401e0ec504938e`
- Method: Rolling fixed-length walk-forward; parameters selected on training only, then tested once on the next unseen window
- Equity file: concatenated per-fold OOS equity; each fold restarts from the configured initial balance
- Resolved config SHA-256: `a9a3227acf5ca408ce58d76780a91cddeae3f5de65f3daf71d49058d400deda3`

## Validation summary

```json
{
  "folds": 20,
  "oos_expectancy_r": 0.314195,
  "oos_net_profit": 175.5,
  "oos_profit_factor": 1.59873,
  "oos_trades": 30,
  "positive_fold_ratio": 0.35,
  "positive_folds": 7,
  "positive_year_profit_concentration_pct": 27.056506,
  "stress_net_profit": 171.17,
  "worst_fold_max_drawdown_pct": 1.319995,
  "worst_fold_stress_profit_factor": 0.0,
  "yearly_oos_net_profit": {
    "2003": 50.88,
    "2004": -116.43,
    "2005": -28.48,
    "2006": 47.25,
    "2007": 20.05,
    "2017": 49.21,
    "2018": 67.62,
    "2019": -1.76,
    "2020": 87.17
  }
}
```

## Gates

- enough_folds: PASS
- enough_oos_trades: PASS
- oos_profit_factor: PASS
- positive_fold_ratio: FAIL
- drawdown: PASS
- positive_stress_net: PASS
- stress_profit_factor: FAIL
- profit_concentration: PASS
- data_coverage: PASS
- ea_static_review: PASS
- mt5_compile_and_real_tick_test: FAIL
- demo_forward_test: FAIL
- data_coverage: PASS
- mt5_compile_and_real_tick_test: NOT RUN
- demo_forward_test: NOT RUN

## Required next step

Use broker-specific XAUUSD data, compile the EA in MetaEditor, then run MT5 Every tick based on real ticks with variable spread. Keep new entries disabled until independent out-of-sample and demo forward tests are acceptable.

The Python engine uses bars and a stop-first ambiguity rule. Its results can differ from MT5 tick execution, swaps, broker contract size, news blackout behavior and actual slippage.
