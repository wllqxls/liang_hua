# Hourly Extreme-Momentum Reversion Event Factor Report

- Scope: read-only event research; no strategy or trade is created.
- Data: BTC/USDT and ETH/USDT, UTC calendar years 2024 and 2025, 1h candles.
- Two-bar extreme: both bodies >= `0.0050` and cumulative move >= `0.0150`.
- Single-bar extreme: body >= `0.0050` and close beyond Bollinger(20, 2).
- Event B: contrarian close movement >= `0.5 * ATR(14)` within one or two bars.
- Fixed complete round-trip cost: `0.0014`.
- One event is retained per continuous same-direction extreme episode.
- Design: `docs/research/hourly-extreme-reversion-design.md`.
- Code revision: `b1083f3`.

| Slice | Horizon | A events | B conversion % | Avg gross return % | Avg net return % | Net Profit Factor | Status |
|---|---|---:|---:|---:|---:|---:|---|
| BTC/USDT 2024 | 1h | 571 | 26.80 | -0.0199 | -0.1599 | 0.554 | COMPLETE_YEAR |
| BTC/USDT 2024 | 2h | 571 | 39.05 | -0.0421 | -0.1821 | 0.596 | COMPLETE_YEAR |
| BTC/USDT 2025 | 1h | 423 | 22.22 | -0.0519 | -0.1919 | 0.464 | COMPLETE_YEAR |
| BTC/USDT 2025 | 2h | 423 | 35.93 | -0.0320 | -0.1720 | 0.614 | COMPLETE_YEAR |
| ETH/USDT 2024 | 1h | 664 | 26.36 | 0.0347 | -0.1053 | 0.698 | COMPLETE_YEAR |
| ETH/USDT 2024 | 2h | 664 | 41.11 | 0.0155 | -0.1245 | 0.730 | COMPLETE_YEAR |
| ETH/USDT 2025 | 1h | 721 | 21.36 | -0.0802 | -0.2202 | 0.527 | COMPLETE_YEAR |
| ETH/USDT 2025 | 2h | 721 | 34.81 | -0.0288 | -0.1688 | 0.706 | COMPLETE_YEAR |

## Event A trigger composition

- BTC/USDT 2024: BOLLINGER=433, BOTH=52, TWO_BAR=86
- BTC/USDT 2025: BOLLINGER=327, BOTH=40, TWO_BAR=56
- ETH/USDT 2024: BOLLINGER=458, BOTH=77, TWO_BAR=129
- ETH/USDT 2025: BOLLINGER=429, BOTH=101, TWO_BAR=191

## Conclusion

- All net averages negative: `yes`; all net Profit Factors below `1.0`: `yes`.
- Samples per result: `423–721`; this is not a small-sample rejection.
- Positive gross exceptions: ETH/USDT 2024 1h `+0.0347%`, ETH/USDT 2024 2h `+0.0155%`.
- Per the predeclared decision, if every net result is negative, the project stops tuning single-symbol short-horizon extreme-momentum mean-reversion rules. This rejects the tested basic family; it is not a mathematical claim that every possible mean-reversion model is impossible.
