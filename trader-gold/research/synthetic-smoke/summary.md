# Gold EA research result

Status: **SYNTHETIC_ONLY**
Deployment: **MT5_VALIDATION_REQUIRED**

This is an automated research result, not financial advice or a promise of profit.

## Evidence

- Mode: demo
- Data rows: 50112
- Data coverage: 2016-01-04T00:00:00Z to 2024-01-04T00:00:00Z
- Data SHA-256: `10de1d5a01056bdf4e861a8583fa79c47f7366053a21c548b04c580981533486`
- Method: Rolling fixed-length walk-forward; parameters selected on training only, then tested once on the next unseen window
- Equity file: concatenated per-fold OOS equity; each fold restarts from the configured initial balance
- Resolved config SHA-256: `c7326c6cfd520066fecef85d7597a42e2bcf4d0c907ec1a603fbe5481c8ecf46`

## Validation summary

```json
{
  "folds": 6,
  "oos_expectancy_r": 0.938719,
  "oos_net_profit": 29871.44,
  "oos_profit_factor": 7.596818,
  "oos_trades": 1114,
  "positive_fold_ratio": 1.0,
  "positive_folds": 6,
  "positive_year_profit_concentration_pct": 21.193631,
  "stress_net_profit": 28246.0,
  "worst_fold_max_drawdown_pct": 1.690371,
  "worst_fold_stress_profit_factor": 6.713147,
  "yearly_oos_net_profit": {
    "2019": 6098.16,
    "2020": 6330.84,
    "2021": 5886.0,
    "2022": 5996.55,
    "2023": 5398.33,
    "2024": 161.54
  }
}
```

## Gates

- enough_folds: PASS
- enough_oos_trades: PASS
- oos_profit_factor: PASS
- positive_fold_ratio: PASS
- drawdown: PASS
- positive_stress_net: PASS
- stress_profit_factor: PASS
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
