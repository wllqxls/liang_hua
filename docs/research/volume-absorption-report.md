# Volume-Absorption Reversal Event Factor Report

- Scope: read-only event research; no strategy or trade is created.
- Fixed single-symbol round-trip cost: `0.0014`.
- Event A: volume ratio >= 1.5, true range / ATR <= 1.0, three-bar displacement >= 1.0 ATR.
- Event B: within three bars, price moves at least 0.5 event ATR in the contrarian direction.
- Timeframes: 5m and 15m are executed as a predeclared parallel comparison.
- 15m executed: `yes`.
- Design: `docs/research/volume-absorption-design.md`.
- Code revision: `628e21f`.

## BTC/USDT / 5m / 2024

- Status: `COMPLETE_YEAR`
- Event A: `1381`
- Event B: `729`
- A→B conversion: `52.79%`
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2024_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2024_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 1381 | 0.0186 | -0.1214 | 37.94 | 0.501 | yes |
| direction | BUY | 634 | 0.0351 | -0.1049 | 39.43 | 0.544 | yes |
| direction | SELL | 747 | 0.0045 | -0.1355 | 36.68 | 0.468 | yes |
| volume_shock_tertile | HIGH | 461 | 0.0376 | -0.1024 | 35.57 | 0.569 | yes |
| volume_shock_tertile | LOW | 460 | 0.0087 | -0.1313 | 38.26 | 0.479 | yes |
| volume_shock_tertile | MID | 460 | 0.0093 | -0.1307 | 40.00 | 0.457 | yes |
| absorption_tertile | HIGH | 461 | 0.0187 | -0.1213 | 34.71 | 0.492 | yes |
| absorption_tertile | LOW | 460 | -0.0093 | -0.1493 | 37.61 | 0.464 | yes |
| absorption_tertile | MID | 460 | 0.0463 | -0.0937 | 41.52 | 0.559 | yes |

## BTC/USDT / 5m / 2025

- Status: `COMPLETE_YEAR`
- Event A: `1794`
- Event B: `921`
- A→B conversion: `51.34%`
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2025_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2025_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 1794 | -0.0008 | -0.1408 | 30.88 | 0.374 | yes |
| direction | BUY | 909 | -0.0002 | -0.1402 | 31.24 | 0.393 | yes |
| direction | SELL | 885 | -0.0013 | -0.1413 | 30.51 | 0.354 | yes |
| volume_shock_tertile | HIGH | 598 | 0.0227 | -0.1173 | 29.93 | 0.424 | yes |
| volume_shock_tertile | LOW | 598 | -0.0118 | -0.1518 | 31.10 | 0.334 | yes |
| volume_shock_tertile | MID | 598 | -0.0132 | -0.1532 | 31.61 | 0.371 | yes |
| absorption_tertile | HIGH | 598 | -0.0083 | -0.1483 | 28.76 | 0.309 | yes |
| absorption_tertile | LOW | 598 | 0.0099 | -0.1301 | 32.61 | 0.450 | yes |
| absorption_tertile | MID | 598 | -0.0039 | -0.1439 | 31.27 | 0.357 | yes |

## ETH/USDT / 5m / 2024

- Status: `COMPLETE_YEAR`
- Event A: `1368`
- Event B: `694`
- A→B conversion: `50.73%`
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2024_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2024_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 1368 | 0.0196 | -0.1204 | 40.94 | 0.580 | yes |
| direction | BUY | 610 | 0.0116 | -0.1284 | 41.15 | 0.574 | yes |
| direction | SELL | 758 | 0.0261 | -0.1139 | 40.77 | 0.586 | yes |
| volume_shock_tertile | HIGH | 456 | 0.0120 | -0.1280 | 40.79 | 0.557 | yes |
| volume_shock_tertile | LOW | 456 | 0.0052 | -0.1348 | 38.82 | 0.515 | yes |
| volume_shock_tertile | MID | 456 | 0.0416 | -0.0984 | 43.20 | 0.665 | yes |
| absorption_tertile | HIGH | 456 | 0.0061 | -0.1339 | 39.47 | 0.525 | yes |
| absorption_tertile | LOW | 456 | 0.0342 | -0.1058 | 41.45 | 0.616 | yes |
| absorption_tertile | MID | 456 | 0.0185 | -0.1215 | 41.89 | 0.599 | yes |

## ETH/USDT / 5m / 2025

- Status: `COMPLETE_YEAR`
- Event A: `1300`
- Event B: `613`
- A→B conversion: `47.15%`
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2025_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2025_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 1300 | -0.0237 | -0.1637 | 39.46 | 0.523 | yes |
| direction | BUY | 633 | 0.0196 | -0.1204 | 41.55 | 0.644 | yes |
| direction | SELL | 667 | -0.0648 | -0.2048 | 37.48 | 0.411 | yes |
| volume_shock_tertile | HIGH | 434 | -0.0244 | -0.1644 | 40.32 | 0.522 | yes |
| volume_shock_tertile | LOW | 433 | -0.0435 | -0.1835 | 39.49 | 0.447 | yes |
| volume_shock_tertile | MID | 433 | -0.0032 | -0.1432 | 38.57 | 0.594 | yes |
| absorption_tertile | HIGH | 434 | 0.0107 | -0.1293 | 38.25 | 0.577 | yes |
| absorption_tertile | LOW | 433 | -0.0175 | -0.1575 | 42.26 | 0.573 | yes |
| absorption_tertile | MID | 433 | -0.0644 | -0.2044 | 37.88 | 0.425 | yes |

## BTC/USDT / 15m / 2024

- Status: `COMPLETE_YEAR`
- Event A: `319`
- Event B: `167`
- A→B conversion: `52.35%`
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_15m_2024_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_15m_2024_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 319 | 0.0050 | -0.1350 | 39.18 | 0.495 | yes |
| direction | BUY | 145 | 0.0309 | -0.1091 | 38.62 | 0.584 | no |
| direction | SELL | 174 | -0.0166 | -0.1566 | 39.66 | 0.424 | no |
| volume_shock_tertile | HIGH | 107 | 0.0184 | -0.1216 | 34.58 | 0.513 | no |
| volume_shock_tertile | LOW | 106 | -0.0818 | -0.2218 | 38.68 | 0.348 | no |
| volume_shock_tertile | MID | 106 | 0.0783 | -0.0617 | 44.34 | 0.710 | no |
| absorption_tertile | HIGH | 107 | 0.0187 | -0.1213 | 35.51 | 0.450 | no |
| absorption_tertile | LOW | 106 | -0.0231 | -0.1631 | 39.62 | 0.476 | no |
| absorption_tertile | MID | 106 | 0.0193 | -0.1207 | 42.45 | 0.555 | no |

## BTC/USDT / 15m / 2025

- Status: `COMPLETE_YEAR`
- Event A: `439`
- Event B: `209`
- A→B conversion: `47.61%`
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_15m_2025_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_15m_2025_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 439 | -0.0280 | -0.1680 | 32.57 | 0.314 | yes |
| direction | BUY | 227 | -0.0322 | -0.1722 | 32.16 | 0.315 | yes |
| direction | SELL | 212 | -0.0236 | -0.1636 | 33.02 | 0.313 | yes |
| volume_shock_tertile | HIGH | 147 | -0.0448 | -0.1848 | 29.25 | 0.263 | no |
| volume_shock_tertile | LOW | 146 | -0.0222 | -0.1622 | 34.93 | 0.379 | no |
| volume_shock_tertile | MID | 146 | -0.0170 | -0.1570 | 33.56 | 0.295 | no |
| absorption_tertile | HIGH | 147 | -0.0348 | -0.1748 | 31.97 | 0.267 | no |
| absorption_tertile | LOW | 146 | -0.0482 | -0.1882 | 34.25 | 0.322 | no |
| absorption_tertile | MID | 146 | -0.0011 | -0.1411 | 31.51 | 0.355 | no |

## ETH/USDT / 15m / 2024

- Status: `COMPLETE_YEAR`
- Event A: `335`
- Event B: `168`
- A→B conversion: `50.15%`
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_15m_2024_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_15m_2024_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 335 | 0.0827 | -0.0573 | 47.76 | 0.797 | yes |
| direction | BUY | 142 | 0.1483 | 0.0083 | 50.70 | 1.029 | no |
| direction | SELL | 193 | 0.0344 | -0.1056 | 45.60 | 0.622 | no |
| volume_shock_tertile | HIGH | 112 | -0.0276 | -0.1676 | 43.75 | 0.500 | no |
| volume_shock_tertile | LOW | 111 | 0.2079 | 0.0679 | 53.15 | 1.388 | no |
| volume_shock_tertile | MID | 112 | 0.0688 | -0.0712 | 46.43 | 0.789 | no |
| absorption_tertile | HIGH | 112 | 0.1122 | -0.0278 | 42.86 | 0.881 | no |
| absorption_tertile | LOW | 111 | 0.0818 | -0.0582 | 49.55 | 0.784 | no |
| absorption_tertile | MID | 112 | 0.0540 | -0.0860 | 50.89 | 0.751 | no |

## ETH/USDT / 15m / 2025

- Status: `COMPLETE_YEAR`
- Event A: `340`
- Event B: `162`
- A→B conversion: `47.65%`
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_15m_2025_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_15m_2025_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 340 | 0.0006 | -0.1394 | 39.41 | 0.555 | yes |
| direction | BUY | 161 | 0.0202 | -0.1198 | 44.10 | 0.641 | no |
| direction | SELL | 179 | -0.0170 | -0.1570 | 35.20 | 0.468 | no |
| volume_shock_tertile | HIGH | 114 | 0.0419 | -0.0981 | 41.23 | 0.672 | no |
| volume_shock_tertile | LOW | 113 | 0.0180 | -0.1220 | 44.25 | 0.574 | no |
| volume_shock_tertile | MID | 113 | -0.0584 | -0.1984 | 32.74 | 0.438 | no |
| absorption_tertile | HIGH | 114 | -0.0571 | -0.1971 | 37.72 | 0.365 | no |
| absorption_tertile | LOW | 113 | 0.0055 | -0.1345 | 38.05 | 0.586 | no |
| absorption_tertile | MID | 113 | 0.0539 | -0.0861 | 42.48 | 0.717 | no |
