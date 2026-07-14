# Volume-Absorption Reversal Event Factor Report

- Scope: read-only event research; no strategy or trade is created.
- Fixed single-symbol round-trip cost: `0.0014`.
- Event A: volume ratio >= 3.0, true range / ATR <= 0.8, three-bar displacement >= 1.0 ATR.
- Event B: within three bars, price moves at least 0.5 event ATR in the contrarian direction.
- 15m gate: all four BTC/ETH 2024/2025 5m slices must have positive net one-hour average return.
- 15m executed: `no`.
- Design: `docs/research/volume-absorption-design.md`.
- Code revision: `e2354b3`.

## BTC/USDT / 5m / 2024

- Status: `COMPLETE_YEAR`
- Event A: `12`
- Event B: `7`
- A→B conversion: `58.33%`
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2024_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2024_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 12 | 0.1094 | -0.0306 | 33.33 | 0.755 | no |
| direction | BUY | 5 | 0.1367 | -0.0033 | 40.00 | 0.979 | no |
| direction | SELL | 7 | 0.0899 | -0.0501 | 28.57 | 0.521 | no |
| volume_shock_tertile | HIGH | 4 | 0.0256 | -0.1144 | 25.00 | 0.357 | no |
| volume_shock_tertile | LOW | 4 | -0.0286 | -0.1686 | 0.00 | 0.000 | no |
| volume_shock_tertile | MID | 4 | 0.3313 | 0.1913 | 75.00 | 7.643 | no |
| absorption_tertile | HIGH | 4 | 0.2457 | 0.1057 | 50.00 | 2.401 | no |
| absorption_tertile | LOW | 4 | 0.1106 | -0.0294 | 25.00 | 0.706 | no |
| absorption_tertile | MID | 4 | -0.0281 | -0.1681 | 25.00 | 0.160 | no |

## BTC/USDT / 5m / 2025

- Status: `COMPLETE_YEAR`
- Event A: `60`
- Event B: `38`
- A→B conversion: `63.33%`
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2025_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2025_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 60 | -0.0226 | -0.1626 | 18.33 | 0.186 | no |
| direction | BUY | 34 | 0.0020 | -0.1380 | 17.65 | 0.294 | no |
| direction | SELL | 26 | -0.0548 | -0.1948 | 19.23 | 0.053 | no |
| volume_shock_tertile | HIGH | 20 | -0.0549 | -0.1949 | 5.00 | 0.029 | no |
| volume_shock_tertile | LOW | 20 | -0.0322 | -0.1722 | 20.00 | 0.338 | no |
| volume_shock_tertile | MID | 20 | 0.0192 | -0.1208 | 30.00 | 0.129 | no |
| absorption_tertile | HIGH | 20 | 0.0102 | -0.1298 | 15.00 | 0.038 | no |
| absorption_tertile | LOW | 20 | -0.0355 | -0.1755 | 25.00 | 0.350 | no |
| absorption_tertile | MID | 20 | -0.0426 | -0.1826 | 15.00 | 0.063 | no |

## ETH/USDT / 5m / 2024

- Status: `COMPLETE_YEAR`
- Event A: `27`
- Event B: `14`
- A→B conversion: `51.85%`
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2024_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2024_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 27 | -0.0184 | -0.1584 | 37.04 | 0.554 | no |
| direction | BUY | 9 | -0.3082 | -0.4482 | 22.22 | 0.134 | no |
| direction | SELL | 18 | 0.1264 | -0.0136 | 44.44 | 0.950 | no |
| volume_shock_tertile | HIGH | 9 | -0.1618 | -0.3018 | 44.44 | 0.141 | no |
| volume_shock_tertile | LOW | 9 | -0.2376 | -0.3776 | 33.33 | 0.202 | no |
| volume_shock_tertile | MID | 9 | 0.3441 | 0.2041 | 33.33 | 1.846 | no |
| absorption_tertile | HIGH | 9 | -0.0186 | -0.1586 | 33.33 | 0.256 | no |
| absorption_tertile | LOW | 9 | 0.2736 | 0.1336 | 55.56 | 1.427 | no |
| absorption_tertile | MID | 9 | -0.3104 | -0.4504 | 22.22 | 0.165 | no |

## ETH/USDT / 5m / 2025

- Status: `COMPLETE_YEAR`
- Event A: `46`
- Event B: `22`
- A→B conversion: `47.83%`
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2025_volume_absorption_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2025_volume_absorption_b.csv`

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| overall | ALL | 46 | 0.1918 | 0.0518 | 52.17 | 1.242 | no |
| direction | BUY | 20 | 0.2894 | 0.1494 | 60.00 | 1.762 | no |
| direction | SELL | 26 | 0.1168 | -0.0232 | 46.15 | 0.898 | no |
| volume_shock_tertile | HIGH | 16 | 0.2336 | 0.0936 | 37.50 | 1.761 | no |
| volume_shock_tertile | LOW | 15 | 0.0566 | -0.0834 | 66.67 | 0.749 | no |
| volume_shock_tertile | MID | 15 | 0.2825 | 0.1425 | 53.33 | 1.736 | no |
| absorption_tertile | HIGH | 16 | 0.2388 | 0.0988 | 50.00 | 1.540 | no |
| absorption_tertile | LOW | 15 | 0.2236 | 0.0836 | 60.00 | 1.251 | no |
| absorption_tertile | MID | 15 | 0.1099 | -0.0301 | 46.67 | 0.766 | no |

## Stop decision

At least one 5m BTC/ETH 2024/2025 slice did not have a positive net one-hour average return. Per the frozen gate, 15m was not run.
