# Extreme-Momentum Mean-Reversion Event Factor Report

- Scope: read-only event research; this report creates no strategy or trade.
- Fixed round-trip cost: `0.0014`.
- Event A is scored in its contrarian direction: upper extreme = SELL, lower extreme = BUY.
- Event B only measures whether the immediately next 5m close returned past the then-known Bollinger middle band.
- Hard rejection: any slice with A→B conversion below 10% or fewer than 200 A events cannot become a strategy.
- Design: `docs/research/momentum-reversion-design.md`.
- Code revision: `823fbd6`.

## BTC/USDT / 5m / 2024

- Status: `COMPLETE_YEAR`
- Decision: `REJECT_NO_STRATEGY`
- Event A (extreme momentum): `723`
- Event B (next-bar middle-band reversion): `0`
- A→B conversion: `0.00%`
- Rejection reason: A→B conversion 0.00% < 10%
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2024_momentum_reversion_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2024_momentum_reversion_b.csv`

| A holding period | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor |
|---|---:|---:|---:|---:|
| 5m | -0.0048 | -0.1448 | 28.77 | 0.258 |
| 15m | -0.0172 | -0.1572 | 36.93 | 0.372 |
| 1h | -0.0146 | -0.1546 | 43.15 | 0.574 |
| 4h | -0.0860 | -0.2260 | 44.54 | 0.612 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 343 | 0.0376 | -0.1024 | 45.48 | 0.720 | yes |
| direction | SELL | 380 | -0.0617 | -0.2017 | 41.05 | 0.440 | yes |
| rsi_extremity_tertile | HIGH | 241 | -0.0123 | -0.1523 | 43.98 | 0.634 | yes |
| rsi_extremity_tertile | LOW | 241 | 0.0110 | -0.1290 | 43.15 | 0.567 | yes |
| rsi_extremity_tertile | MID | 241 | -0.0426 | -0.1826 | 42.32 | 0.512 | yes |
| band_excess_tertile | HIGH | 241 | -0.0355 | -0.1755 | 41.91 | 0.576 | yes |
| band_excess_tertile | LOW | 241 | -0.0189 | -0.1589 | 42.32 | 0.509 | yes |
| band_excess_tertile | MID | 241 | 0.0106 | -0.1294 | 45.23 | 0.632 | yes |

## BTC/USDT / 5m / 2025

- Status: `COMPLETE_YEAR`
- Decision: `REJECT_NO_STRATEGY`
- Event A (extreme momentum): `648`
- Event B (next-bar middle-band reversion): `0`
- A→B conversion: `0.00%`
- Rejection reason: A→B conversion 0.00% < 10%
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2025_momentum_reversion_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2025_momentum_reversion_b.csv`

| A holding period | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor |
|---|---:|---:|---:|---:|
| 5m | 0.0028 | -0.1372 | 23.92 | 0.214 |
| 15m | 0.0073 | -0.1327 | 33.18 | 0.380 |
| 1h | -0.0019 | -0.1419 | 39.51 | 0.536 |
| 4h | 0.0151 | -0.1249 | 46.91 | 0.733 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 338 | 0.0308 | -0.1092 | 40.83 | 0.621 | yes |
| direction | SELL | 310 | -0.0375 | -0.1775 | 38.06 | 0.455 | yes |
| rsi_extremity_tertile | HIGH | 216 | -0.0026 | -0.1426 | 42.13 | 0.560 | yes |
| rsi_extremity_tertile | LOW | 216 | 0.0223 | -0.1177 | 39.81 | 0.577 | yes |
| rsi_extremity_tertile | MID | 216 | -0.0253 | -0.1653 | 36.57 | 0.476 | yes |
| band_excess_tertile | HIGH | 216 | -0.0365 | -0.1765 | 40.28 | 0.496 | yes |
| band_excess_tertile | LOW | 216 | 0.0020 | -0.1380 | 37.96 | 0.495 | yes |
| band_excess_tertile | MID | 216 | 0.0289 | -0.1111 | 40.28 | 0.622 | yes |

## BTC/USDT / 5m / 2026

- Status: `PARTIAL_YEAR`
- Decision: `REJECT_NO_STRATEGY`
- Event A (extreme momentum): `400`
- Event B (next-bar middle-band reversion): `2`
- A→B conversion: `0.50%`
- Rejection reason: A→B conversion 0.50% < 10%
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2026_momentum_reversion_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2026_momentum_reversion_b.csv`

| A holding period | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor |
|---|---:|---:|---:|---:|
| 5m | 0.0249 | -0.1151 | 24.25 | 0.242 |
| 15m | 0.0231 | -0.1169 | 34.75 | 0.414 |
| 1h | 0.0189 | -0.1211 | 40.75 | 0.562 |
| 4h | 0.0191 | -0.1209 | 45.50 | 0.745 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 209 | -0.0106 | -0.1506 | 39.71 | 0.520 | yes |
| direction | SELL | 191 | 0.0512 | -0.0888 | 41.88 | 0.623 | no |
| rsi_extremity_tertile | HIGH | 134 | 0.0518 | -0.0882 | 44.03 | 0.703 | no |
| rsi_extremity_tertile | LOW | 133 | 0.0331 | -0.1069 | 36.84 | 0.563 | no |
| rsi_extremity_tertile | MID | 133 | -0.0285 | -0.1685 | 41.35 | 0.416 | no |
| band_excess_tertile | HIGH | 134 | 0.0880 | -0.0520 | 41.79 | 0.802 | no |
| band_excess_tertile | LOW | 133 | 0.0003 | -0.1397 | 41.35 | 0.461 | no |
| band_excess_tertile | MID | 133 | -0.0322 | -0.1722 | 39.10 | 0.441 | no |

## ETH/USDT / 5m / 2024

- Status: `COMPLETE_YEAR`
- Decision: `REJECT_NO_STRATEGY`
- Event A (extreme momentum): `749`
- Event B (next-bar middle-band reversion): `0`
- A→B conversion: `0.00%`
- Rejection reason: A→B conversion 0.00% < 10%
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2024_momentum_reversion_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2024_momentum_reversion_b.csv`

| A holding period | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor |
|---|---:|---:|---:|---:|
| 5m | 0.0115 | -0.1285 | 33.38 | 0.378 |
| 15m | 0.0206 | -0.1194 | 42.46 | 0.549 |
| 1h | 0.0706 | -0.0694 | 55.01 | 0.820 |
| 4h | 0.1090 | -0.0310 | 54.47 | 0.948 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 364 | 0.0708 | -0.0692 | 56.87 | 0.840 | yes |
| direction | SELL | 385 | 0.0704 | -0.0696 | 53.25 | 0.798 | yes |
| rsi_extremity_tertile | HIGH | 250 | 0.0671 | -0.0729 | 57.60 | 0.829 | yes |
| rsi_extremity_tertile | LOW | 249 | 0.0850 | -0.0550 | 55.42 | 0.850 | yes |
| rsi_extremity_tertile | MID | 250 | 0.0598 | -0.0802 | 52.00 | 0.780 | yes |
| band_excess_tertile | HIGH | 250 | 0.0721 | -0.0679 | 51.20 | 0.844 | yes |
| band_excess_tertile | LOW | 249 | 0.0988 | -0.0412 | 59.04 | 0.883 | yes |
| band_excess_tertile | MID | 250 | 0.0410 | -0.0990 | 54.80 | 0.735 | yes |

## ETH/USDT / 5m / 2025

- Status: `COMPLETE_YEAR`
- Decision: `REJECT_NO_STRATEGY`
- Event A (extreme momentum): `735`
- Event B (next-bar middle-band reversion): `1`
- A→B conversion: `0.14%`
- Rejection reason: A→B conversion 0.14% < 10%
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2025_momentum_reversion_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2025_momentum_reversion_b.csv`

| A holding period | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor |
|---|---:|---:|---:|---:|
| 5m | -0.0144 | -0.1544 | 34.69 | 0.335 |
| 15m | -0.0121 | -0.1521 | 41.63 | 0.489 |
| 1h | -0.0589 | -0.1989 | 45.99 | 0.572 |
| 4h | -0.1224 | -0.2624 | 47.35 | 0.673 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 373 | -0.0575 | -0.1975 | 46.65 | 0.619 | yes |
| direction | SELL | 362 | -0.0604 | -0.2004 | 45.30 | 0.511 | yes |
| rsi_extremity_tertile | HIGH | 245 | -0.1520 | -0.2920 | 43.27 | 0.503 | yes |
| rsi_extremity_tertile | LOW | 245 | 0.0011 | -0.1389 | 47.76 | 0.623 | yes |
| rsi_extremity_tertile | MID | 245 | -0.0259 | -0.1659 | 46.94 | 0.622 | yes |
| band_excess_tertile | HIGH | 245 | -0.0751 | -0.2151 | 44.90 | 0.601 | yes |
| band_excess_tertile | LOW | 245 | -0.0179 | -0.1579 | 48.57 | 0.608 | yes |
| band_excess_tertile | MID | 245 | -0.0838 | -0.2238 | 44.49 | 0.506 | yes |

## ETH/USDT / 5m / 2026

- Status: `PARTIAL_YEAR`
- Decision: `REJECT_NO_STRATEGY`
- Event A (extreme momentum): `416`
- Event B (next-bar middle-band reversion): `0`
- A→B conversion: `0.00%`
- Rejection reason: A→B conversion 0.00% < 10%
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2026_momentum_reversion_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2026_momentum_reversion_b.csv`

| A holding period | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor |
|---|---:|---:|---:|---:|
| 5m | 0.0068 | -0.1332 | 29.81 | 0.313 |
| 15m | 0.0117 | -0.1283 | 41.35 | 0.496 |
| 1h | 0.0184 | -0.1216 | 46.39 | 0.667 |
| 4h | -0.0562 | -0.1962 | 45.91 | 0.705 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 226 | 0.0299 | -0.1101 | 47.35 | 0.706 | yes |
| direction | SELL | 190 | 0.0046 | -0.1354 | 45.26 | 0.619 | no |
| rsi_extremity_tertile | HIGH | 139 | -0.0833 | -0.2233 | 47.48 | 0.509 | no |
| rsi_extremity_tertile | LOW | 138 | 0.0246 | -0.1154 | 43.48 | 0.670 | no |
| rsi_extremity_tertile | MID | 139 | 0.1139 | -0.0261 | 48.20 | 0.910 | no |
| band_excess_tertile | HIGH | 139 | 0.0507 | -0.0893 | 48.92 | 0.745 | no |
| band_excess_tertile | LOW | 138 | -0.0365 | -0.1765 | 43.48 | 0.554 | no |
| band_excess_tertile | MID | 139 | 0.0406 | -0.0994 | 46.76 | 0.717 | no |
