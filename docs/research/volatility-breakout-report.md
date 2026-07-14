# Volatility-Compression Breakout Event Factor Report

- Scope: read-only A/B event research; this report creates no strategy or trade.
- Fixed round-trip cost: `0.0014`.
- Event A has no direction, so it reports sample count and A→B conversion only; return and Profit Factor apply to directional event B.
- Buckets with fewer than 200 B events are descriptive only.
- Design: `docs/research/volatility-breakout-design.md`.
- Code revision: `d107992`.

## BTC/USDT / 5m + 1h / 2025

- Status: `PARTIAL_YEAR`
- Event A (compression): `182`
- Event B (first directional breakout after A): `10`
- A→B conversion: `5.49%`
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2025_volatility_compression_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2025_volatility_breakout_b.csv`

| A→B one-hour metric | Value |
|---|---:|
| Avg gross return % | -0.0557 |
| Avg net return % | -0.1957 |
| Net win rate % | 30.00 |
| Net Profit Factor | 0.309 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 6 | -0.1634 | -0.3034 | 33.33 | 0.058 | no |
| direction | SELL | 4 | 0.1059 | -0.0341 | 25.00 | 0.848 | no |
| compression_tertile | HIGH | 4 | 0.1193 | -0.0207 | 50.00 | 0.575 | no |
| compression_tertile | LOW | 3 | -0.1027 | -0.2427 | 33.33 | 0.511 | no |
| compression_tertile | MID | 3 | -0.2421 | -0.3821 | 0.00 | 0.000 | no |
| mid_distance_tertile | HIGH | 4 | 0.0435 | -0.0965 | 25.00 | 0.193 | no |
| mid_distance_tertile | LOW | 3 | -0.0657 | -0.2057 | 33.33 | 0.552 | no |
| mid_distance_tertile | MID | 3 | -0.1780 | -0.3180 | 33.33 | 0.020 | no |

## BTC/USDT / 5m + 1h / 2026

- Status: `PARTIAL_YEAR`
- Event A (compression): `150`
- Event B (first directional breakout after A): `7`
- A→B conversion: `4.67%`
- A dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2026_volatility_compression_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/BTC_USDT_5m_2026_volatility_breakout_b.csv`

| A→B one-hour metric | Value |
|---|---:|
| Avg gross return % | -0.1996 |
| Avg net return % | -0.3396 |
| Net win rate % | 0.00 |
| Net Profit Factor | 0.000 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 5 | -0.1776 | -0.3176 | 0.00 | 0.000 | no |
| direction | SELL | 2 | -0.2546 | -0.3946 | 0.00 | 0.000 | no |
| compression_tertile | HIGH | 3 | -0.1730 | -0.3130 | 0.00 | 0.000 | no |
| compression_tertile | LOW | 2 | 0.0156 | -0.1244 | 0.00 | 0.000 | no |
| compression_tertile | MID | 2 | -0.4548 | -0.5948 | 0.00 | 0.000 | no |
| mid_distance_tertile | HIGH | 3 | -0.2884 | -0.4284 | 0.00 | 0.000 | no |
| mid_distance_tertile | LOW | 2 | -0.0005 | -0.1405 | 0.00 | 0.000 | no |
| mid_distance_tertile | MID | 2 | -0.2656 | -0.4056 | 0.00 | 0.000 | no |

## ETH/USDT / 5m + 1h / 2025

- Status: `COMPLETE_YEAR`
- Event A (compression): `176`
- Event B (first directional breakout after A): `6`
- A→B conversion: `3.41%`
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2025_volatility_compression_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2025_volatility_breakout_b.csv`

| A→B one-hour metric | Value |
|---|---:|
| Avg gross return % | -0.4030 |
| Avg net return % | -0.5430 |
| Net win rate % | 16.67 |
| Net Profit Factor | 0.036 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 2 | -0.1577 | -0.2977 | 0.00 | 0.000 | no |
| direction | SELL | 4 | -0.5257 | -0.6657 | 25.00 | 0.044 | no |
| compression_tertile | HIGH | 2 | -0.8438 | -0.9838 | 0.00 | 0.000 | no |
| compression_tertile | LOW | 2 | -0.4069 | -0.5469 | 0.00 | 0.000 | no |
| compression_tertile | MID | 2 | 0.0417 | -0.0983 | 50.00 | 0.385 | no |
| mid_distance_tertile | HIGH | 2 | -0.4374 | -0.5774 | 0.00 | 0.000 | no |
| mid_distance_tertile | LOW | 2 | -0.4287 | -0.5687 | 0.00 | 0.000 | no |
| mid_distance_tertile | MID | 2 | -0.3429 | -0.4829 | 50.00 | 0.113 | no |

## ETH/USDT / 5m + 1h / 2026

- Status: `PARTIAL_YEAR`
- Event A (compression): `125`
- Event B (first directional breakout after A): `9`
- A→B conversion: `7.20%`
- A dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2026_volatility_compression_a.csv`
- B dataset: `C:/KUN/liang_hua/results/research/ETH_USDT_5m_2026_volatility_breakout_b.csv`

| A→B one-hour metric | Value |
|---|---:|
| Avg gross return % | -0.1502 |
| Avg net return % | -0.2902 |
| Net win rate % | 22.22 |
| Net Profit Factor | 0.060 |

| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |
|---|---|---:|---:|---:|---:|---:|---|
| direction | BUY | 6 | -0.1545 | -0.2945 | 33.33 | 0.086 | no |
| direction | SELL | 3 | -0.1414 | -0.2814 | 0.00 | 0.000 | no |
| compression_tertile | HIGH | 3 | 0.0681 | -0.0719 | 33.33 | 0.354 | no |
| compression_tertile | LOW | 3 | -0.2907 | -0.4307 | 0.00 | 0.000 | no |
| compression_tertile | MID | 3 | -0.2279 | -0.3679 | 33.33 | 0.042 | no |
| mid_distance_tertile | HIGH | 3 | -0.2378 | -0.3778 | 33.33 | 0.095 | no |
| mid_distance_tertile | LOW | 3 | -0.0132 | -0.1532 | 33.33 | 0.095 | no |
| mid_distance_tertile | MID | 3 | -0.1994 | -0.3394 | 0.00 | 0.000 | no |
