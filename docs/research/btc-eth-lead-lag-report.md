# BTC→ETH Short-Term Lead-Lag Event Factor Report

- Scope: read-only event research; no strategy or trade is created.
- Data read: synchronized BTC/ETH 5m candles from UTC 2024 and 2025 only; 2026 remains unused.
- BTC impulse threshold: `1.0 ATR(14)` over three bars.
- ETH lag rule: same direction and normalized displacement <= `0.5` of BTC.
- Fixed ETH single-leg complete round-trip cost: `0.0014`.
- Primary gate horizon: `15m`; 5m/30m/1h are diagnostic only.
- Confidence interval: deterministic UTC-calendar-day block bootstrap, 95%.
- Design: `docs/research/btc-eth-lead-lag-design.md`.
- Code revision: `4038309`.

| Year | Horizon | Samples | Gross positive % | Avg gross % | Avg net % | Break-even cost % | Net mean 95% CI % | Net PF | Status |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2024 | 5m | 5929 | 47.75 | -0.0020 | -0.1420 | -0.0020 | [-0.1467, -0.1372] | 0.122 | COMPLETE_YEAR |
| 2024 | 15m | 5929 | 47.48 | -0.0025 | -0.1425 | -0.0025 | [-0.1506, -0.1346] | 0.286 | COMPLETE_YEAR |
| 2024 | 30m | 5929 | 48.44 | 0.0019 | -0.1381 | 0.0019 | [-0.1493, -0.1269] | 0.413 | COMPLETE_YEAR |
| 2024 | 1h | 5929 | 48.44 | -0.0032 | -0.1432 | -0.0032 | [-0.1604, -0.1255] | 0.506 | COMPLETE_YEAR |
| 2025 | 5m | 7276 | 48.98 | 0.0018 | -0.1382 | 0.0018 | [-0.1431, -0.1333] | 0.152 | COMPLETE_YEAR |
| 2025 | 15m | 7276 | 47.40 | -0.0020 | -0.1420 | -0.0020 | [-0.1513, -0.1335] | 0.314 | COMPLETE_YEAR |
| 2025 | 30m | 7276 | 47.55 | -0.0051 | -0.1451 | -0.0051 | [-0.1568, -0.1331] | 0.429 | COMPLETE_YEAR |
| 2025 | 1h | 7276 | 47.88 | -0.0067 | -0.1467 | -0.0067 | [-0.1636, -0.1291] | 0.540 | COMPLETE_YEAR |

## Event direction composition

- 2024: BUY=3233, SELL=2696
- 2025: BUY=3768, SELL=3508

## Frozen 15m gate

- Passed: `no`.
- Required in both years: samples >= 200, average net return > 0, net PF >= 1.15, and net mean 95% CI lower bound > 0.
- Strategy generated: `no`.

## Conclusion

- All tested horizons have negative net means: `yes`.
- The primary 15m gross mean is negative in both years: `yes`.
- If the primary gross mean is already negative, lower execution cost cannot turn this frozen event definition into a stable edge.
