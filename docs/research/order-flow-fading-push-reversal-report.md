# 主动资金退潮后的短期回调研究报告

- 状态：只读因子研究；不是策略回测、模拟盘或实盘建议。
- 设计：`docs/research/order-flow-fading-push-reversal-design.md`。
- 数据：2024 用于实现和描述，2025 是独立验证；2026 未读取。
- 成本：完整往返 `0.0014`；30m 是唯一主检验窗口。
- 代码版本：`e955320`。

## 事件与数据排除

| 标的 | 年份 | 冷却后事件数 | 冷却前合格行 | 因 OI 缺口排除行 | 事件 CSV |
|---|---:|---:|---:|---:|---|
| BTCUSDT | 2024 | 147 | 151 | 27 | `results\research\order_flow\BTCUSDT_15m_2024_fading_push_reversal.csv` |
| ETHUSDT | 2024 | 199 | 208 | 27 | `results\research\order_flow\ETHUSDT_15m_2024_fading_push_reversal.csv` |
| BTCUSDT | 2025 | 199 | 206 | 25 | `results\research\order_flow\BTCUSDT_15m_2025_fading_push_reversal.csv` |
| ETHUSDT | 2025 | 171 | 180 | 25 | `results\research\order_flow\ETHUSDT_15m_2025_fading_push_reversal.csv` |
## BTCUSDT 2024

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 30m | overall | ALL | 147 | -0.000114 | -0.001514 | 21.77% | 0.237 | no |
| 30m | taker_buy_ratio_tertile | HIGH | 49 | -0.000263 | -0.001663 | 18.37% | 0.220 | no |
| 30m | taker_buy_ratio_tertile | LOW | 49 | -0.000036 | -0.001436 | 24.49% | 0.216 | no |
| 30m | taker_buy_ratio_tertile | MID | 49 | -0.000043 | -0.001443 | 22.45% | 0.274 | no |
| 30m | oi_change_tertile | HIGH | 48 | -0.000080 | -0.001480 | 22.92% | 0.305 | no |
| 30m | oi_change_tertile | LOW | 48 | 0.000152 | -0.001248 | 25.00% | 0.236 | no |
| 30m | oi_change_tertile | MID | 47 | -0.000285 | -0.001685 | 19.15% | 0.197 | no |
| 30m | oi_change_tertile | UNAVAILABLE | 4 | -0.001687 | -0.003087 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | HIGH | 49 | 0.000509 | -0.000891 | 34.69% | 0.539 | no |
| 30m | volatility_tertile | LOW | 49 | -0.000233 | -0.001633 | 14.29% | 0.092 | no |
| 30m | volatility_tertile | MID | 49 | -0.000617 | -0.002017 | 16.33% | 0.092 | no |
| 30m | funding_tertile | HIGH | 49 | -0.000072 | -0.001472 | 22.45% | 0.296 | no |
| 30m | funding_tertile | LOW | 49 | -0.000217 | -0.001617 | 24.49% | 0.229 | no |
| 30m | funding_tertile | MID | 49 | -0.000052 | -0.001452 | 18.37% | 0.176 | no |
| 1h | overall | ALL | 147 | -0.000164 | -0.001564 | 27.89% | 0.334 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 49 | 0.000281 | -0.001119 | 28.57% | 0.463 | no |
| 1h | taker_buy_ratio_tertile | LOW | 49 | 0.000253 | -0.001147 | 32.65% | 0.433 | no |
| 1h | taker_buy_ratio_tertile | MID | 49 | -0.001027 | -0.002427 | 22.45% | 0.175 | no |
| 1h | oi_change_tertile | HIGH | 48 | 0.000024 | -0.001376 | 29.17% | 0.395 | no |
| 1h | oi_change_tertile | LOW | 48 | 0.000310 | -0.001090 | 31.25% | 0.456 | no |
| 1h | oi_change_tertile | MID | 47 | -0.000469 | -0.001869 | 23.40% | 0.226 | no |
| 1h | oi_change_tertile | UNAVAILABLE | 4 | -0.004537 | -0.005937 | 25.00% | 0.103 | no |
| 1h | volatility_tertile | HIGH | 49 | 0.000866 | -0.000534 | 38.78% | 0.751 | no |
| 1h | volatility_tertile | LOW | 49 | -0.000533 | -0.001933 | 20.41% | 0.127 | no |
| 1h | volatility_tertile | MID | 49 | -0.000826 | -0.002226 | 24.49% | 0.171 | no |
| 1h | funding_tertile | HIGH | 49 | -0.000733 | -0.002133 | 32.65% | 0.359 | no |
| 1h | funding_tertile | LOW | 49 | -0.000132 | -0.001532 | 24.49% | 0.255 | no |
| 1h | funding_tertile | MID | 49 | 0.000372 | -0.001028 | 26.53% | 0.384 | no |

## ETHUSDT 2024

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 30m | overall | ALL | 199 | 0.000084 | -0.001316 | 28.64% | 0.354 | no |
| 30m | taker_buy_ratio_tertile | HIGH | 66 | 0.000430 | -0.000970 | 30.30% | 0.434 | no |
| 30m | taker_buy_ratio_tertile | LOW | 67 | -0.000309 | -0.001709 | 26.87% | 0.274 | no |
| 30m | taker_buy_ratio_tertile | MID | 66 | 0.000137 | -0.001263 | 28.79% | 0.381 | no |
| 30m | oi_change_tertile | HIGH | 66 | 0.000191 | -0.001209 | 28.79% | 0.444 | no |
| 30m | oi_change_tertile | LOW | 66 | -0.000275 | -0.001675 | 30.30% | 0.213 | no |
| 30m | oi_change_tertile | MID | 65 | 0.000354 | -0.001046 | 27.69% | 0.422 | no |
| 30m | oi_change_tertile | UNAVAILABLE | 2 | -0.000331 | -0.001731 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | HIGH | 66 | 0.000597 | -0.000803 | 37.88% | 0.623 | no |
| 30m | volatility_tertile | LOW | 67 | -0.000524 | -0.001924 | 19.40% | 0.100 | no |
| 30m | volatility_tertile | MID | 66 | 0.000189 | -0.001211 | 28.79% | 0.341 | no |
| 30m | funding_tertile | HIGH | 66 | 0.000240 | -0.001160 | 36.36% | 0.386 | no |
| 30m | funding_tertile | LOW | 67 | 0.000286 | -0.001114 | 25.37% | 0.414 | no |
| 30m | funding_tertile | MID | 66 | -0.000276 | -0.001676 | 24.24% | 0.277 | no |
| 1h | overall | ALL | 199 | -0.000319 | -0.001719 | 31.16% | 0.385 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 66 | 0.000172 | -0.001228 | 30.30% | 0.436 | no |
| 1h | taker_buy_ratio_tertile | LOW | 67 | -0.001343 | -0.002743 | 25.37% | 0.254 | no |
| 1h | taker_buy_ratio_tertile | MID | 66 | 0.000228 | -0.001172 | 37.88% | 0.535 | no |
| 1h | oi_change_tertile | HIGH | 66 | 0.000072 | -0.001328 | 33.33% | 0.485 | no |
| 1h | oi_change_tertile | LOW | 66 | -0.000857 | -0.002257 | 24.24% | 0.230 | no |
| 1h | oi_change_tertile | MID | 65 | -0.000259 | -0.001659 | 35.38% | 0.430 | no |
| 1h | oi_change_tertile | UNAVAILABLE | 2 | 0.002528 | 0.001128 | 50.00% | 1.629 | no |
| 1h | volatility_tertile | HIGH | 66 | 0.000688 | -0.000712 | 42.42% | 0.750 | no |
| 1h | volatility_tertile | LOW | 67 | -0.001521 | -0.002921 | 16.42% | 0.082 | no |
| 1h | volatility_tertile | MID | 66 | -0.000108 | -0.001508 | 34.85% | 0.358 | no |
| 1h | funding_tertile | HIGH | 66 | -0.000052 | -0.001452 | 27.27% | 0.464 | no |
| 1h | funding_tertile | LOW | 67 | -0.000003 | -0.001403 | 37.31% | 0.446 | no |
| 1h | funding_tertile | MID | 66 | -0.000908 | -0.002308 | 28.79% | 0.267 | no |

## BTCUSDT 2025

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 30m | overall | ALL | 199 | 0.000208 | -0.001192 | 29.15% | 0.315 | no |
| 30m | taker_buy_ratio_tertile | HIGH | 66 | -0.000290 | -0.001690 | 21.21% | 0.166 | no |
| 30m | taker_buy_ratio_tertile | LOW | 67 | -0.000119 | -0.001519 | 22.39% | 0.245 | no |
| 30m | taker_buy_ratio_tertile | MID | 66 | 0.001038 | -0.000362 | 43.94% | 0.692 | no |
| 30m | oi_change_tertile | HIGH | 66 | 0.000396 | -0.001004 | 34.85% | 0.409 | no |
| 30m | oi_change_tertile | LOW | 67 | 0.000390 | -0.001010 | 31.34% | 0.344 | no |
| 30m | oi_change_tertile | MID | 66 | -0.000164 | -0.001564 | 21.21% | 0.211 | no |
| 30m | volatility_tertile | HIGH | 66 | 0.000272 | -0.001128 | 37.88% | 0.435 | no |
| 30m | volatility_tertile | LOW | 67 | 0.000046 | -0.001354 | 16.42% | 0.127 | no |
| 30m | volatility_tertile | MID | 66 | 0.000309 | -0.001091 | 33.33% | 0.347 | no |
| 30m | funding_tertile | HIGH | 66 | 0.000475 | -0.000925 | 31.82% | 0.374 | no |
| 30m | funding_tertile | LOW | 67 | 0.000070 | -0.001330 | 23.88% | 0.238 | no |
| 30m | funding_tertile | MID | 66 | 0.000081 | -0.001319 | 31.82% | 0.339 | no |
| 1h | overall | ALL | 199 | 0.000319 | -0.001081 | 34.67% | 0.475 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 66 | -0.000422 | -0.001822 | 30.30% | 0.310 | no |
| 1h | taker_buy_ratio_tertile | LOW | 67 | 0.000400 | -0.001000 | 35.82% | 0.523 | no |
| 1h | taker_buy_ratio_tertile | MID | 66 | 0.000978 | -0.000422 | 37.88% | 0.708 | no |
| 1h | oi_change_tertile | HIGH | 66 | 0.001203 | -0.000197 | 42.42% | 0.877 | no |
| 1h | oi_change_tertile | LOW | 67 | 0.000573 | -0.000827 | 34.33% | 0.540 | no |
| 1h | oi_change_tertile | MID | 66 | -0.000822 | -0.002222 | 27.27% | 0.203 | no |
| 1h | volatility_tertile | HIGH | 66 | 0.000691 | -0.000709 | 39.39% | 0.680 | no |
| 1h | volatility_tertile | LOW | 67 | 0.000067 | -0.001333 | 28.36% | 0.298 | no |
| 1h | volatility_tertile | MID | 66 | 0.000204 | -0.001196 | 36.36% | 0.421 | no |
| 1h | funding_tertile | HIGH | 66 | 0.000161 | -0.001239 | 30.30% | 0.468 | no |
| 1h | funding_tertile | LOW | 67 | 0.000344 | -0.001056 | 32.84% | 0.465 | no |
| 1h | funding_tertile | MID | 66 | 0.000453 | -0.000947 | 40.91% | 0.496 | no |

## ETHUSDT 2025

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 30m | overall | ALL | 171 | 0.000127 | -0.001273 | 35.67% | 0.495 | no |
| 30m | taker_buy_ratio_tertile | HIGH | 57 | 0.000416 | -0.000984 | 35.09% | 0.564 | no |
| 30m | taker_buy_ratio_tertile | LOW | 57 | -0.000589 | -0.001989 | 31.58% | 0.316 | no |
| 30m | taker_buy_ratio_tertile | MID | 57 | 0.000555 | -0.000845 | 40.35% | 0.648 | no |
| 30m | oi_change_tertile | HIGH | 57 | 0.000883 | -0.000517 | 45.61% | 0.785 | no |
| 30m | oi_change_tertile | LOW | 57 | -0.000117 | -0.001517 | 33.33% | 0.296 | no |
| 30m | oi_change_tertile | MID | 57 | -0.000384 | -0.001784 | 28.07% | 0.406 | no |
| 30m | volatility_tertile | HIGH | 57 | 0.000376 | -0.001024 | 47.37% | 0.677 | no |
| 30m | volatility_tertile | LOW | 57 | -0.000010 | -0.001410 | 29.82% | 0.326 | no |
| 30m | volatility_tertile | MID | 57 | 0.000016 | -0.001384 | 29.82% | 0.398 | no |
| 30m | funding_tertile | HIGH | 57 | -0.000457 | -0.001857 | 31.58% | 0.318 | no |
| 30m | funding_tertile | LOW | 57 | -0.000094 | -0.001494 | 35.09% | 0.462 | no |
| 30m | funding_tertile | MID | 57 | 0.000933 | -0.000467 | 40.35% | 0.773 | no |
| 1h | overall | ALL | 171 | -0.000430 | -0.001830 | 34.50% | 0.455 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 57 | -0.000205 | -0.001605 | 35.09% | 0.477 | no |
| 1h | taker_buy_ratio_tertile | LOW | 57 | -0.000985 | -0.002385 | 31.58% | 0.390 | no |
| 1h | taker_buy_ratio_tertile | MID | 57 | -0.000098 | -0.001498 | 36.84% | 0.515 | no |
| 1h | oi_change_tertile | HIGH | 57 | 0.000168 | -0.001232 | 42.11% | 0.631 | no |
| 1h | oi_change_tertile | LOW | 57 | -0.001423 | -0.002823 | 28.07% | 0.224 | no |
| 1h | oi_change_tertile | MID | 57 | -0.000034 | -0.001434 | 33.33% | 0.536 | no |
| 1h | volatility_tertile | HIGH | 57 | 0.000054 | -0.001346 | 38.60% | 0.657 | no |
| 1h | volatility_tertile | LOW | 57 | -0.000840 | -0.002240 | 31.58% | 0.310 | no |
| 1h | volatility_tertile | MID | 57 | -0.000502 | -0.001902 | 33.33% | 0.343 | no |
| 1h | funding_tertile | HIGH | 57 | -0.000791 | -0.002191 | 38.60% | 0.377 | no |
| 1h | funding_tertile | LOW | 57 | -0.000662 | -0.002062 | 31.58% | 0.413 | no |
| 1h | funding_tertile | MID | 57 | 0.000164 | -0.001236 | 33.33% | 0.593 | no |

## 预先声明的 2025 验证门槛

- 条件：BTCUSDT、ETHUSDT 均在 30m 总体桶达到样本数 >= 200、平均成本后收益 > 0、Profit Factor >= 1.15。
- 结果：`未通过；不得进入候选策略或回测调参`。
- 任一细分桶样本不足 200 时仅作描述，不形成策略结论。
