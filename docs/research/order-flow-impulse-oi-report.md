# 订单流冲击与 OI 确认事件研究报告

- 状态：只读因子研究；不是策略回测、模拟盘或实盘建议。
- 设计：`docs/research/order-flow-impulse-oi-design.md`。
- 数据：Binance USD-M Futures 增强 5m K 线、metrics 与 fundingRate；2024 用于实现，2025 为独立验证，2026 未读取。
- 成本：完整往返 `0.0014`；15m 是唯一主检验窗口。
- 代码版本：`7d6c9bc`。

## 事件与数据排除

| 标的 | 年份 | 冷却后事件数 | 冷却前合格行 | 因 OI 缺口排除行 | 事件 CSV |
|---|---:|---:|---:|---:|---|
| BTCUSDT | 2024 | 424 | 487 | 120 | `results\research\order_flow\BTCUSDT_5m_2024_impulse_oi_events.csv` |
| ETHUSDT | 2024 | 351 | 381 | 120 | `results\research\order_flow\ETHUSDT_5m_2024_impulse_oi_events.csv` |
| BTCUSDT | 2025 | 331 | 385 | 126 | `results\research\order_flow\BTCUSDT_5m_2025_impulse_oi_events.csv` |
| ETHUSDT | 2025 | 266 | 291 | 126 | `results\research\order_flow\ETHUSDT_5m_2025_impulse_oi_events.csv` |
## BTCUSDT 2024

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 5m | overall | ALL | 424 | -0.000127 | -0.001527 | 16.75% | 0.136 | yes |
| 5m | direction | BUY | 238 | -0.000123 | -0.001523 | 15.97% | 0.145 | yes |
| 5m | direction | SELL | 186 | -0.000131 | -0.001531 | 17.74% | 0.125 | no |
| 5m | imbalance_tertile | HIGH | 141 | -0.000141 | -0.001541 | 14.89% | 0.092 | no |
| 5m | imbalance_tertile | LOW | 142 | -0.000099 | -0.001499 | 18.31% | 0.172 | no |
| 5m | imbalance_tertile | MID | 141 | -0.000139 | -0.001539 | 17.02% | 0.142 | no |
| 5m | oi_change_tertile | HIGH | 138 | -0.000342 | -0.001742 | 16.67% | 0.109 | no |
| 5m | oi_change_tertile | LOW | 139 | 0.000245 | -0.001155 | 19.42% | 0.226 | no |
| 5m | oi_change_tertile | MID | 138 | -0.000281 | -0.001681 | 14.49% | 0.090 | no |
| 5m | oi_change_tertile | UNAVAILABLE | 9 | -0.000199 | -0.001599 | 11.11% | 0.166 | no |
| 5m | volatility_tertile | HIGH | 141 | -0.000312 | -0.001712 | 21.99% | 0.156 | no |
| 5m | volatility_tertile | LOW | 142 | -0.000134 | -0.001534 | 9.86% | 0.051 | no |
| 5m | volatility_tertile | MID | 141 | 0.000067 | -0.001333 | 18.44% | 0.195 | no |
| 5m | funding_tertile | HIGH | 141 | -0.000082 | -0.001482 | 16.31% | 0.120 | no |
| 5m | funding_tertile | LOW | 142 | -0.000136 | -0.001536 | 19.72% | 0.156 | no |
| 5m | funding_tertile | MID | 141 | -0.000162 | -0.001562 | 14.18% | 0.131 | no |
| 15m | overall | ALL | 424 | -0.000006 | -0.001406 | 25.94% | 0.339 | yes |
| 15m | direction | BUY | 238 | 0.000051 | -0.001349 | 25.63% | 0.366 | yes |
| 15m | direction | SELL | 186 | -0.000079 | -0.001479 | 26.34% | 0.305 | no |
| 15m | imbalance_tertile | HIGH | 141 | 0.000123 | -0.001277 | 25.53% | 0.372 | no |
| 15m | imbalance_tertile | LOW | 142 | 0.000056 | -0.001344 | 29.58% | 0.385 | no |
| 15m | imbalance_tertile | MID | 141 | -0.000199 | -0.001599 | 22.70% | 0.262 | no |
| 15m | oi_change_tertile | HIGH | 138 | -0.000017 | -0.001417 | 27.54% | 0.386 | no |
| 15m | oi_change_tertile | LOW | 139 | 0.000427 | -0.000973 | 28.06% | 0.471 | no |
| 15m | oi_change_tertile | MID | 138 | -0.000433 | -0.001833 | 23.19% | 0.198 | no |
| 15m | oi_change_tertile | UNAVAILABLE | 9 | 0.000020 | -0.001380 | 11.11% | 0.011 | no |
| 15m | volatility_tertile | HIGH | 141 | -0.000000 | -0.001400 | 34.75% | 0.432 | no |
| 15m | volatility_tertile | LOW | 142 | -0.000284 | -0.001684 | 13.38% | 0.127 | no |
| 15m | volatility_tertile | MID | 141 | 0.000267 | -0.001133 | 29.79% | 0.430 | no |
| 15m | funding_tertile | HIGH | 141 | 0.000357 | -0.001043 | 27.66% | 0.489 | no |
| 15m | funding_tertile | LOW | 142 | -0.000211 | -0.001611 | 23.24% | 0.284 | no |
| 15m | funding_tertile | MID | 141 | -0.000164 | -0.001564 | 26.95% | 0.252 | no |
| 1h | overall | ALL | 424 | 0.000062 | -0.001338 | 33.25% | 0.552 | yes |
| 1h | direction | BUY | 238 | 0.000493 | -0.000907 | 36.13% | 0.663 | yes |
| 1h | direction | SELL | 186 | -0.000491 | -0.001891 | 29.57% | 0.439 | no |
| 1h | imbalance_tertile | HIGH | 141 | 0.000115 | -0.001285 | 30.50% | 0.547 | no |
| 1h | imbalance_tertile | LOW | 142 | 0.000407 | -0.000993 | 39.44% | 0.671 | no |
| 1h | imbalance_tertile | MID | 141 | -0.000339 | -0.001739 | 29.79% | 0.441 | no |
| 1h | oi_change_tertile | HIGH | 138 | -0.000068 | -0.001468 | 34.06% | 0.554 | no |
| 1h | oi_change_tertile | LOW | 139 | 0.000900 | -0.000500 | 36.69% | 0.796 | no |
| 1h | oi_change_tertile | MID | 138 | -0.000589 | -0.001989 | 30.43% | 0.383 | no |
| 1h | oi_change_tertile | UNAVAILABLE | 9 | -0.000923 | -0.002323 | 11.11% | 0.251 | no |
| 1h | volatility_tertile | HIGH | 141 | 0.000312 | -0.001088 | 37.59% | 0.691 | no |
| 1h | volatility_tertile | LOW | 142 | -0.000254 | -0.001654 | 25.35% | 0.324 | no |
| 1h | volatility_tertile | MID | 141 | 0.000129 | -0.001271 | 36.88% | 0.576 | no |
| 1h | funding_tertile | HIGH | 141 | 0.000197 | -0.001203 | 36.88% | 0.617 | no |
| 1h | funding_tertile | LOW | 142 | -0.000473 | -0.001873 | 30.99% | 0.406 | no |
| 1h | funding_tertile | MID | 141 | 0.000465 | -0.000935 | 31.91% | 0.650 | no |

## ETHUSDT 2024

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 5m | overall | ALL | 351 | -0.000047 | -0.001447 | 22.51% | 0.274 | yes |
| 5m | direction | BUY | 185 | 0.000349 | -0.001051 | 25.95% | 0.374 | no |
| 5m | direction | SELL | 166 | -0.000489 | -0.001889 | 18.67% | 0.194 | no |
| 5m | imbalance_tertile | HIGH | 117 | 0.000191 | -0.001209 | 21.37% | 0.307 | no |
| 5m | imbalance_tertile | LOW | 117 | -0.000033 | -0.001433 | 25.64% | 0.290 | no |
| 5m | imbalance_tertile | MID | 117 | -0.000300 | -0.001700 | 20.51% | 0.234 | no |
| 5m | oi_change_tertile | HIGH | 116 | -0.000372 | -0.001772 | 25.00% | 0.259 | no |
| 5m | oi_change_tertile | LOW | 117 | 0.000138 | -0.001262 | 18.80% | 0.275 | no |
| 5m | oi_change_tertile | MID | 116 | 0.000121 | -0.001279 | 24.14% | 0.302 | no |
| 5m | oi_change_tertile | UNAVAILABLE | 2 | -0.001794 | -0.003194 | 0.00% | 0.000 | no |
| 5m | volatility_tertile | HIGH | 117 | -0.000598 | -0.001998 | 23.93% | 0.265 | no |
| 5m | volatility_tertile | LOW | 117 | 0.000050 | -0.001350 | 16.24% | 0.161 | no |
| 5m | volatility_tertile | MID | 117 | 0.000405 | -0.000995 | 27.35% | 0.400 | no |
| 5m | funding_tertile | HIGH | 117 | -0.000216 | -0.001616 | 26.50% | 0.272 | no |
| 5m | funding_tertile | LOW | 117 | -0.000031 | -0.001431 | 17.95% | 0.290 | no |
| 5m | funding_tertile | MID | 117 | 0.000106 | -0.001294 | 23.08% | 0.259 | no |
| 15m | overall | ALL | 351 | 0.000146 | -0.001254 | 28.49% | 0.492 | yes |
| 15m | direction | BUY | 185 | 0.000817 | -0.000583 | 30.27% | 0.715 | no |
| 15m | direction | SELL | 166 | -0.000602 | -0.002002 | 26.51% | 0.321 | no |
| 15m | imbalance_tertile | HIGH | 117 | 0.000763 | -0.000637 | 26.50% | 0.676 | no |
| 15m | imbalance_tertile | LOW | 117 | 0.000490 | -0.000910 | 33.33% | 0.619 | no |
| 15m | imbalance_tertile | MID | 117 | -0.000815 | -0.002215 | 25.64% | 0.275 | no |
| 15m | oi_change_tertile | HIGH | 116 | -0.000421 | -0.001821 | 25.86% | 0.433 | no |
| 15m | oi_change_tertile | LOW | 117 | 0.000385 | -0.001015 | 27.35% | 0.499 | no |
| 15m | oi_change_tertile | MID | 116 | 0.000520 | -0.000880 | 32.76% | 0.590 | no |
| 15m | oi_change_tertile | UNAVAILABLE | 2 | -0.002581 | -0.003981 | 0.00% | 0.000 | no |
| 15m | volatility_tertile | HIGH | 117 | -0.000330 | -0.001730 | 30.77% | 0.485 | no |
| 15m | volatility_tertile | LOW | 117 | 0.000007 | -0.001393 | 21.37% | 0.262 | no |
| 15m | volatility_tertile | MID | 117 | 0.000761 | -0.000639 | 33.33% | 0.705 | no |
| 15m | funding_tertile | HIGH | 117 | -0.000730 | -0.002130 | 24.79% | 0.334 | no |
| 15m | funding_tertile | LOW | 117 | 0.000642 | -0.000758 | 30.77% | 0.657 | no |
| 15m | funding_tertile | MID | 117 | 0.000526 | -0.000874 | 29.91% | 0.564 | no |
| 1h | overall | ALL | 351 | 0.000500 | -0.000900 | 36.47% | 0.735 | yes |
| 1h | direction | BUY | 185 | 0.001037 | -0.000363 | 40.54% | 0.877 | no |
| 1h | direction | SELL | 166 | -0.000097 | -0.001497 | 31.93% | 0.613 | no |
| 1h | imbalance_tertile | HIGH | 117 | 0.000343 | -0.001057 | 30.77% | 0.655 | no |
| 1h | imbalance_tertile | LOW | 117 | 0.000734 | -0.000666 | 41.88% | 0.785 | no |
| 1h | imbalance_tertile | MID | 117 | 0.000424 | -0.000976 | 36.75% | 0.757 | no |
| 1h | oi_change_tertile | HIGH | 116 | -0.000772 | -0.002172 | 33.62% | 0.495 | no |
| 1h | oi_change_tertile | LOW | 117 | 0.001659 | 0.000259 | 33.33% | 1.087 | no |
| 1h | oi_change_tertile | MID | 116 | 0.000661 | -0.000739 | 43.10% | 0.742 | no |
| 1h | oi_change_tertile | UNAVAILABLE | 2 | -0.002819 | -0.004219 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | HIGH | 117 | 0.001397 | -0.000003 | 41.03% | 0.999 | no |
| 1h | volatility_tertile | LOW | 117 | 0.000388 | -0.001012 | 34.19% | 0.593 | no |
| 1h | volatility_tertile | MID | 117 | -0.000284 | -0.001684 | 34.19% | 0.511 | no |
| 1h | funding_tertile | HIGH | 117 | -0.000646 | -0.002046 | 35.90% | 0.526 | no |
| 1h | funding_tertile | LOW | 117 | 0.001196 | -0.000204 | 29.91% | 0.938 | no |
| 1h | funding_tertile | MID | 117 | 0.000951 | -0.000449 | 43.59% | 0.824 | no |

## BTCUSDT 2025

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 5m | overall | ALL | 331 | -0.000138 | -0.001538 | 15.41% | 0.134 | yes |
| 5m | direction | BUY | 172 | -0.000347 | -0.001747 | 10.47% | 0.068 | no |
| 5m | direction | SELL | 159 | 0.000087 | -0.001313 | 20.75% | 0.214 | no |
| 5m | imbalance_tertile | HIGH | 110 | -0.000134 | -0.001534 | 10.91% | 0.056 | no |
| 5m | imbalance_tertile | LOW | 111 | -0.000229 | -0.001629 | 20.72% | 0.181 | no |
| 5m | imbalance_tertile | MID | 110 | -0.000052 | -0.001452 | 14.55% | 0.154 | no |
| 5m | oi_change_tertile | HIGH | 110 | -0.000427 | -0.001827 | 12.73% | 0.067 | no |
| 5m | oi_change_tertile | LOW | 110 | 0.000047 | -0.001353 | 16.36% | 0.172 | no |
| 5m | oi_change_tertile | MID | 110 | -0.000034 | -0.001434 | 17.27% | 0.176 | no |
| 5m | oi_change_tertile | UNAVAILABLE | 1 | -0.000148 | -0.001548 | 0.00% | 0.000 | no |
| 5m | volatility_tertile | HIGH | 110 | 0.000026 | -0.001374 | 29.09% | 0.269 | no |
| 5m | volatility_tertile | LOW | 111 | -0.000131 | -0.001531 | 7.21% | 0.030 | no |
| 5m | volatility_tertile | MID | 110 | -0.000311 | -0.001711 | 10.00% | 0.088 | no |
| 5m | funding_tertile | HIGH | 110 | -0.000518 | -0.001918 | 13.64% | 0.107 | no |
| 5m | funding_tertile | LOW | 111 | -0.000031 | -0.001431 | 11.71% | 0.140 | no |
| 5m | funding_tertile | MID | 110 | 0.000133 | -0.001267 | 20.91% | 0.167 | no |
| 15m | overall | ALL | 331 | -0.000320 | -0.001720 | 24.17% | 0.261 | yes |
| 15m | direction | BUY | 172 | -0.000519 | -0.001919 | 19.19% | 0.174 | no |
| 15m | direction | SELL | 159 | -0.000104 | -0.001504 | 29.56% | 0.356 | no |
| 15m | imbalance_tertile | HIGH | 110 | -0.000476 | -0.001876 | 19.09% | 0.146 | no |
| 15m | imbalance_tertile | LOW | 111 | -0.000397 | -0.001797 | 28.83% | 0.323 | no |
| 15m | imbalance_tertile | MID | 110 | -0.000085 | -0.001485 | 24.55% | 0.303 | no |
| 15m | oi_change_tertile | HIGH | 110 | -0.000705 | -0.002105 | 25.45% | 0.188 | no |
| 15m | oi_change_tertile | LOW | 110 | -0.000108 | -0.001508 | 24.55% | 0.260 | no |
| 15m | oi_change_tertile | MID | 110 | -0.000149 | -0.001549 | 22.73% | 0.344 | no |
| 15m | oi_change_tertile | UNAVAILABLE | 1 | 0.000009 | -0.001391 | 0.00% | 0.000 | no |
| 15m | volatility_tertile | HIGH | 110 | -0.000460 | -0.001860 | 30.00% | 0.324 | no |
| 15m | volatility_tertile | LOW | 111 | -0.000262 | -0.001662 | 18.92% | 0.132 | no |
| 15m | volatility_tertile | MID | 110 | -0.000238 | -0.001638 | 23.64% | 0.295 | no |
| 15m | funding_tertile | HIGH | 110 | -0.000657 | -0.002057 | 24.55% | 0.218 | no |
| 15m | funding_tertile | LOW | 111 | 0.000114 | -0.001286 | 26.13% | 0.343 | no |
| 15m | funding_tertile | MID | 110 | -0.000421 | -0.001821 | 21.82% | 0.242 | no |
| 1h | overall | ALL | 331 | -0.000072 | -0.001472 | 30.82% | 0.509 | yes |
| 1h | direction | BUY | 172 | -0.000479 | -0.001879 | 24.42% | 0.365 | no |
| 1h | direction | SELL | 159 | 0.000367 | -0.001033 | 37.74% | 0.660 | no |
| 1h | imbalance_tertile | HIGH | 110 | -0.000176 | -0.001576 | 30.91% | 0.447 | no |
| 1h | imbalance_tertile | LOW | 111 | 0.000196 | -0.001204 | 29.73% | 0.616 | no |
| 1h | imbalance_tertile | MID | 110 | -0.000240 | -0.001640 | 31.82% | 0.454 | no |
| 1h | oi_change_tertile | HIGH | 110 | -0.000629 | -0.002029 | 31.82% | 0.391 | no |
| 1h | oi_change_tertile | LOW | 110 | -0.000009 | -0.001409 | 29.09% | 0.484 | no |
| 1h | oi_change_tertile | MID | 110 | 0.000370 | -0.001030 | 30.91% | 0.651 | no |
| 1h | oi_change_tertile | UNAVAILABLE | 1 | 0.005551 | 0.004151 | 100.00% | ∞ | no |
| 1h | volatility_tertile | HIGH | 110 | 0.000066 | -0.001334 | 37.27% | 0.614 | no |
| 1h | volatility_tertile | LOW | 111 | 0.000153 | -0.001247 | 31.53% | 0.497 | no |
| 1h | volatility_tertile | MID | 110 | -0.000438 | -0.001838 | 23.64% | 0.398 | no |
| 1h | funding_tertile | HIGH | 110 | 0.000113 | -0.001287 | 30.91% | 0.557 | no |
| 1h | funding_tertile | LOW | 111 | -0.000048 | -0.001448 | 30.63% | 0.489 | no |
| 1h | funding_tertile | MID | 110 | -0.000283 | -0.001683 | 30.91% | 0.483 | no |

## ETHUSDT 2025

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 5m | overall | ALL | 266 | 0.000289 | -0.001111 | 24.44% | 0.400 | yes |
| 5m | direction | BUY | 140 | -0.000148 | -0.001548 | 22.14% | 0.213 | no |
| 5m | direction | SELL | 126 | 0.000776 | -0.000624 | 26.98% | 0.637 | no |
| 5m | imbalance_tertile | HIGH | 89 | 0.000817 | -0.000583 | 31.46% | 0.564 | no |
| 5m | imbalance_tertile | LOW | 89 | 0.000331 | -0.001069 | 25.84% | 0.469 | no |
| 5m | imbalance_tertile | MID | 88 | -0.000287 | -0.001687 | 15.91% | 0.235 | no |
| 5m | oi_change_tertile | HIGH | 89 | 0.000615 | -0.000785 | 25.84% | 0.576 | no |
| 5m | oi_change_tertile | LOW | 89 | -0.000032 | -0.001432 | 22.47% | 0.222 | no |
| 5m | oi_change_tertile | MID | 88 | 0.000285 | -0.001115 | 25.00% | 0.400 | no |
| 5m | volatility_tertile | HIGH | 89 | 0.000369 | -0.001031 | 29.21% | 0.504 | no |
| 5m | volatility_tertile | LOW | 89 | -0.000008 | -0.001408 | 17.98% | 0.126 | no |
| 5m | volatility_tertile | MID | 88 | 0.000510 | -0.000890 | 26.14% | 0.522 | no |
| 5m | funding_tertile | HIGH | 89 | 0.000064 | -0.001336 | 22.47% | 0.307 | no |
| 5m | funding_tertile | LOW | 89 | 0.000290 | -0.001110 | 25.84% | 0.345 | no |
| 5m | funding_tertile | MID | 88 | 0.000517 | -0.000883 | 25.00% | 0.542 | no |
| 15m | overall | ALL | 266 | 0.000474 | -0.000926 | 33.46% | 0.586 | yes |
| 15m | direction | BUY | 140 | 0.000103 | -0.001297 | 32.86% | 0.429 | no |
| 15m | direction | SELL | 126 | 0.000887 | -0.000513 | 34.13% | 0.767 | no |
| 15m | imbalance_tertile | HIGH | 89 | 0.001118 | -0.000282 | 40.45% | 0.813 | no |
| 15m | imbalance_tertile | LOW | 89 | 0.000355 | -0.001045 | 28.09% | 0.614 | no |
| 15m | imbalance_tertile | MID | 88 | -0.000057 | -0.001457 | 31.82% | 0.418 | no |
| 15m | oi_change_tertile | HIGH | 89 | 0.000729 | -0.000671 | 31.46% | 0.731 | no |
| 15m | oi_change_tertile | LOW | 89 | 0.000636 | -0.000764 | 40.45% | 0.625 | no |
| 15m | oi_change_tertile | MID | 88 | 0.000052 | -0.001348 | 28.41% | 0.383 | no |
| 15m | volatility_tertile | HIGH | 89 | 0.000589 | -0.000811 | 37.08% | 0.693 | no |
| 15m | volatility_tertile | LOW | 89 | 0.000228 | -0.001172 | 25.84% | 0.328 | no |
| 15m | volatility_tertile | MID | 88 | 0.000607 | -0.000793 | 37.50% | 0.660 | no |
| 15m | funding_tertile | HIGH | 89 | -0.000250 | -0.001650 | 24.72% | 0.325 | no |
| 15m | funding_tertile | LOW | 89 | 0.000209 | -0.001191 | 34.83% | 0.475 | no |
| 15m | funding_tertile | MID | 88 | 0.001474 | 0.000074 | 40.91% | 1.037 | no |
| 1h | overall | ALL | 266 | 0.000067 | -0.001333 | 39.47% | 0.634 | yes |
| 1h | direction | BUY | 140 | 0.000349 | -0.001051 | 41.43% | 0.684 | no |
| 1h | direction | SELL | 126 | -0.000247 | -0.001647 | 37.30% | 0.587 | no |
| 1h | imbalance_tertile | HIGH | 89 | 0.000888 | -0.000512 | 47.19% | 0.808 | no |
| 1h | imbalance_tertile | LOW | 89 | -0.000508 | -0.001908 | 33.71% | 0.568 | no |
| 1h | imbalance_tertile | MID | 88 | -0.000183 | -0.001583 | 37.50% | 0.587 | no |
| 1h | oi_change_tertile | HIGH | 89 | -0.000310 | -0.001710 | 35.96% | 0.575 | no |
| 1h | oi_change_tertile | LOW | 89 | 0.000844 | -0.000556 | 41.57% | 0.819 | no |
| 1h | oi_change_tertile | MID | 88 | -0.000338 | -0.001738 | 40.91% | 0.546 | no |
| 1h | volatility_tertile | HIGH | 89 | -0.001120 | -0.002520 | 39.33% | 0.517 | no |
| 1h | volatility_tertile | LOW | 89 | 0.000140 | -0.001260 | 34.83% | 0.503 | no |
| 1h | volatility_tertile | MID | 88 | 0.001192 | -0.000208 | 44.32% | 0.934 | no |
| 1h | funding_tertile | HIGH | 89 | -0.000630 | -0.002030 | 37.08% | 0.468 | no |
| 1h | funding_tertile | LOW | 89 | -0.000608 | -0.002008 | 37.08% | 0.486 | no |
| 1h | funding_tertile | MID | 88 | 0.001453 | 0.000053 | 44.32% | 1.017 | no |

## 预先声明的 2025 验证门槛

- 条件：BTCUSDT、ETHUSDT 均在 15m 总体桶达到样本数 >= 200、平均成本后收益 > 0、Profit Factor >= 1.15。
- 结果：`未通过；不得进入候选策略或回测调参`。
- 任一细分桶样本不足 200 时仅作描述，不形成策略结论。
