# Unified Rejected-Event Research Matrix

- Each hypothesis is pooled only at its predeclared representative horizon.
- All net returns deduct the same single-symbol complete round-trip cost `0.0014`.
- Break-even cost equals the average gross return; a negative value means no non-negative execution cost can rescue the pooled mean.
- The 95% interval is a deterministic source-slice × UTC-day block bootstrap of the net mean.
- Pooled results are descriptive and do not replace the stricter cross-year and cross-symbol rejection already recorded in each report.
- Code revision: `4038309`.

| Hypothesis | Primary horizon | Data scope | Slices | Events | Avg gross % | Avg net % | Break-even cost % | Net mean 95% CI % | Net PF | Status |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Key-level breakout/reversal | 1h | BTC/ETH 5m+15m, 2025 | 4 | 40590 | -0.0084 | -0.1484 | -0.0084 | [-0.1609, -0.1357] | 0.527 | COMPLETE |
| Volatility-compression breakout | 1h | BTC/ETH 5m, 2025 | 2 | 16 | -0.1859 | -0.3259 | -0.1859 | [-0.5411, -0.0983] | 0.160 | COMPLETE |
| Extreme-momentum next-bar reversion | 1h | BTC/ETH 5m, 2024–2025 | 4 | 2855 | -0.0008 | -0.1408 | -0.0008 | [-0.1780, -0.1043] | 0.632 | COMPLETE |
| Volume-absorption reversal | 1h | BTC/ETH 5m+15m, 2024–2025 | 8 | 7276 | 0.0051 | -0.1349 | 0.0051 | [-0.1498, -0.1201] | 0.502 | COMPLETE |
| Three-bar trend inertia | 1h | BTC/ETH 5m+15m, 2024–2025 | 8 | 39172 | -0.0056 | -0.1456 | -0.0056 | [-0.1523, -0.1389] | 0.568 | COMPLETE |
| Hourly extreme-momentum reversion | 2h | BTC/ETH 1h, 2024–2025 | 4 | 2379 | -0.0202 | -0.1602 | -0.0202 | [-0.2089, -0.1111] | 0.673 | COMPLETE |
| BTC→ETH short-term lead-lag | 15m | BTC signal / ETH return, 5m 2024–2025 | 2 | 13205 | -0.0022 | -0.1422 | -0.0022 | [-0.1481, -0.1363] | 0.302 | COMPLETE |

## Reading rule

A useful raw factor would need a positive gross mean large enough to cover cost and a net confidence interval that does not straddle zero. A large event count alone is not evidence of edge.
