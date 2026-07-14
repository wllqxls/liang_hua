# 1h 主动资金退潮后的中短期回调研究报告

- 状态：只读因子研究；不是策略回测、模拟盘或实盘建议。
- 设计：`docs/research/order-flow-hourly-fading-push-design.md`。
- 数据：2024 用于实现和描述，2025 是独立验证；2026 未读取。
- 成本：完整往返 `0.0014`；4h 是唯一主检验窗口。
- 代码版本：`d9ebee3`。

## 事件与数据排除

| 标的 | 年份 | 冷却后事件数 | 冷却前合格行 | 因 OI 缺口排除行 | 事件 CSV |
|---|---:|---:|---:|---:|---|
| BTCUSDT | 2024 | 12 | 12 | 23 | `results\research\order_flow\BTCUSDT_1h_2024_fading_push_reversal.csv` |
| ETHUSDT | 2024 | 10 | 10 | 23 | `results\research\order_flow\ETHUSDT_1h_2024_fading_push_reversal.csv` |
| BTCUSDT | 2025 | 19 | 20 | 29 | `results\research\order_flow\BTCUSDT_1h_2025_fading_push_reversal.csv` |
| ETHUSDT | 2025 | 17 | 18 | 29 | `results\research\order_flow\ETHUSDT_1h_2025_fading_push_reversal.csv` |
## BTCUSDT 2024

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 1h | overall | ALL | 12 | -0.000281 | -0.001681 | 16.67% | 0.095 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 4 | -0.000932 | -0.002332 | 25.00% | 0.099 | no |
| 1h | taker_buy_ratio_tertile | LOW | 4 | -0.000388 | -0.001788 | 0.00% | 0.000 | no |
| 1h | taker_buy_ratio_tertile | MID | 4 | 0.000476 | -0.000924 | 25.00% | 0.226 | no |
| 1h | oi_change_tertile | HIGH | 4 | -0.000917 | -0.002317 | 0.00% | 0.000 | no |
| 1h | oi_change_tertile | LOW | 4 | 0.001330 | -0.000070 | 50.00% | 0.882 | no |
| 1h | oi_change_tertile | MID | 4 | -0.001256 | -0.002656 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | HIGH | 4 | -0.000290 | -0.001690 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | LOW | 4 | -0.000023 | -0.001423 | 25.00% | 0.159 | no |
| 1h | volatility_tertile | MID | 4 | -0.000530 | -0.001930 | 25.00% | 0.118 | no |
| 1h | funding_tertile | HIGH | 4 | 0.000664 | -0.000736 | 50.00% | 0.417 | no |
| 1h | funding_tertile | LOW | 4 | -0.000345 | -0.001745 | 0.00% | 0.000 | no |
| 1h | funding_tertile | MID | 4 | -0.001163 | -0.002563 | 0.00% | 0.000 | no |
| 4h | overall | ALL | 12 | -0.002351 | -0.003751 | 8.33% | 0.203 | no |
| 4h | taker_buy_ratio_tertile | HIGH | 4 | -0.007429 | -0.008829 | 0.00% | 0.000 | no |
| 4h | taker_buy_ratio_tertile | LOW | 4 | 0.003106 | 0.001706 | 25.00% | 2.474 | no |
| 4h | taker_buy_ratio_tertile | MID | 4 | -0.002730 | -0.004130 | 0.00% | 0.000 | no |
| 4h | oi_change_tertile | HIGH | 4 | -0.001735 | -0.003135 | 25.00% | 0.477 | no |
| 4h | oi_change_tertile | LOW | 4 | -0.003425 | -0.004825 | 0.00% | 0.000 | no |
| 4h | oi_change_tertile | MID | 4 | -0.001894 | -0.003294 | 0.00% | 0.000 | no |
| 4h | volatility_tertile | HIGH | 4 | -0.003085 | -0.004485 | 0.00% | 0.000 | no |
| 4h | volatility_tertile | LOW | 4 | -0.000390 | -0.001790 | 0.00% | 0.000 | no |
| 4h | volatility_tertile | MID | 4 | -0.003578 | -0.004978 | 25.00% | 0.365 | no |
| 4h | funding_tertile | HIGH | 4 | -0.004424 | -0.005824 | 0.00% | 0.000 | no |
| 4h | funding_tertile | LOW | 4 | 0.001291 | -0.000109 | 25.00% | 0.963 | no |
| 4h | funding_tertile | MID | 4 | -0.003921 | -0.005321 | 0.00% | 0.000 | no |

## ETHUSDT 2024

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 1h | overall | ALL | 10 | 0.003020 | 0.001620 | 40.00% | 1.555 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 3 | -0.004470 | -0.005870 | 0.00% | 0.000 | no |
| 1h | taker_buy_ratio_tertile | LOW | 4 | 0.002623 | 0.001223 | 75.00% | 1.654 | no |
| 1h | taker_buy_ratio_tertile | MID | 3 | 0.011038 | 0.009638 | 33.33% | 8.056 | no |
| 1h | oi_change_tertile | HIGH | 3 | 0.009464 | 0.008064 | 33.33% | 3.743 | no |
| 1h | oi_change_tertile | LOW | 4 | 0.001214 | -0.000186 | 50.00% | 0.935 | no |
| 1h | oi_change_tertile | MID | 3 | -0.001018 | -0.002418 | 33.33% | 0.182 | no |
| 1h | volatility_tertile | HIGH | 3 | 0.009883 | 0.008483 | 33.33% | 4.365 | no |
| 1h | volatility_tertile | LOW | 4 | 0.002006 | 0.000606 | 50.00% | 1.275 | no |
| 1h | volatility_tertile | MID | 3 | -0.002492 | -0.003892 | 33.33% | 0.088 | no |
| 1h | funding_tertile | HIGH | 3 | 0.002217 | 0.000817 | 66.67% | 1.279 | no |
| 1h | funding_tertile | LOW | 4 | 0.006985 | 0.005585 | 50.00% | 2.893 | no |
| 1h | funding_tertile | MID | 3 | -0.001465 | -0.002865 | 0.00% | 0.000 | no |
| 4h | overall | ALL | 10 | 0.005187 | 0.003787 | 60.00% | 2.036 | no |
| 4h | taker_buy_ratio_tertile | HIGH | 3 | -0.000048 | -0.001448 | 66.67% | 0.631 | no |
| 4h | taker_buy_ratio_tertile | LOW | 4 | 0.001676 | 0.000276 | 50.00% | 1.056 | no |
| 4h | taker_buy_ratio_tertile | MID | 3 | 0.015103 | 0.013703 | 66.67% | 8.890 | no |
| 4h | oi_change_tertile | HIGH | 3 | 0.013460 | 0.012060 | 66.67% | 4.075 | no |
| 4h | oi_change_tertile | LOW | 4 | -0.003805 | -0.005205 | 25.00% | 0.160 | no |
| 4h | oi_change_tertile | MID | 3 | 0.008903 | 0.007503 | 100.00% | ∞ | no |
| 4h | volatility_tertile | HIGH | 3 | 0.010382 | 0.008982 | 66.67% | 2.391 | no |
| 4h | volatility_tertile | LOW | 4 | 0.004827 | 0.003427 | 75.00% | 2.165 | no |
| 4h | volatility_tertile | MID | 3 | 0.000472 | -0.000928 | 33.33% | 0.487 | no |
| 4h | funding_tertile | HIGH | 3 | 0.009177 | 0.007777 | 100.00% | ∞ | no |
| 4h | funding_tertile | LOW | 4 | 0.004352 | 0.002952 | 25.00% | 1.377 | no |
| 4h | funding_tertile | MID | 3 | 0.002310 | 0.000910 | 66.67% | 1.524 | no |

## BTCUSDT 2025

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 1h | overall | ALL | 19 | 0.000292 | -0.001108 | 36.84% | 0.358 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 6 | 0.002185 | 0.000785 | 66.67% | 2.421 | no |
| 1h | taker_buy_ratio_tertile | LOW | 7 | 0.000093 | -0.001307 | 28.57% | 0.225 | no |
| 1h | taker_buy_ratio_tertile | MID | 6 | -0.001368 | -0.002768 | 16.67% | 0.059 | no |
| 1h | oi_change_tertile | HIGH | 6 | 0.002653 | 0.001253 | 66.67% | 3.595 | no |
| 1h | oi_change_tertile | LOW | 7 | -0.000660 | -0.002060 | 28.57% | 0.064 | no |
| 1h | oi_change_tertile | MID | 6 | -0.000958 | -0.002358 | 16.67% | 0.023 | no |
| 1h | volatility_tertile | HIGH | 6 | 0.000325 | -0.001075 | 33.33% | 0.543 | no |
| 1h | volatility_tertile | LOW | 7 | 0.000465 | -0.000935 | 42.86% | 0.309 | no |
| 1h | volatility_tertile | MID | 6 | 0.000058 | -0.001342 | 33.33% | 0.125 | no |
| 1h | funding_tertile | HIGH | 6 | -0.000865 | -0.002265 | 16.67% | 0.113 | no |
| 1h | funding_tertile | LOW | 7 | -0.000968 | -0.002368 | 14.29% | 0.010 | no |
| 1h | funding_tertile | MID | 6 | 0.002919 | 0.001519 | 83.33% | 13.594 | no |
| 4h | overall | ALL | 19 | -0.002297 | -0.003697 | 47.37% | 0.232 | no |
| 4h | taker_buy_ratio_tertile | HIGH | 6 | 0.002929 | 0.001529 | 83.33% | 3.114 | no |
| 4h | taker_buy_ratio_tertile | LOW | 7 | -0.007729 | -0.009129 | 28.57% | 0.042 | no |
| 4h | taker_buy_ratio_tertile | MID | 6 | -0.001186 | -0.002586 | 33.33% | 0.239 | no |
| 4h | oi_change_tertile | HIGH | 6 | 0.002140 | 0.000740 | 66.67% | 2.031 | no |
| 4h | oi_change_tertile | LOW | 7 | -0.000080 | -0.001480 | 42.86% | 0.473 | no |
| 4h | oi_change_tertile | MID | 6 | -0.009320 | -0.010720 | 33.33% | 0.046 | no |
| 4h | volatility_tertile | HIGH | 6 | -0.009556 | -0.010956 | 16.67% | 0.060 | no |
| 4h | volatility_tertile | LOW | 7 | 0.002242 | 0.000842 | 71.43% | 1.686 | no |
| 4h | volatility_tertile | MID | 6 | -0.000333 | -0.001733 | 50.00% | 0.197 | no |
| 4h | funding_tertile | HIGH | 6 | -0.010411 | -0.011811 | 33.33% | 0.034 | no |
| 4h | funding_tertile | LOW | 7 | 0.001256 | -0.000144 | 42.86% | 0.902 | no |
| 4h | funding_tertile | MID | 6 | 0.001672 | 0.000272 | 66.67% | 1.210 | no |

## ETHUSDT 2025

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 1h | overall | ALL | 17 | -0.000402 | -0.001802 | 23.53% | 0.211 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 6 | 0.000423 | -0.000977 | 16.67% | 0.183 | no |
| 1h | taker_buy_ratio_tertile | LOW | 6 | -0.000518 | -0.001918 | 33.33% | 0.355 | no |
| 1h | taker_buy_ratio_tertile | MID | 5 | -0.001253 | -0.002653 | 20.00% | 0.042 | no |
| 1h | oi_change_tertile | HIGH | 6 | -0.000326 | -0.001726 | 33.33% | 0.416 | no |
| 1h | oi_change_tertile | LOW | 6 | -0.000886 | -0.002286 | 16.67% | 0.041 | no |
| 1h | oi_change_tertile | MID | 5 | 0.000088 | -0.001312 | 20.00% | 0.036 | no |
| 1h | volatility_tertile | HIGH | 6 | -0.002113 | -0.003513 | 16.67% | 0.224 | no |
| 1h | volatility_tertile | LOW | 6 | -0.000019 | -0.001419 | 16.67% | 0.064 | no |
| 1h | volatility_tertile | MID | 5 | 0.001192 | -0.000208 | 40.00% | 0.600 | no |
| 1h | funding_tertile | HIGH | 6 | 0.000396 | -0.001004 | 33.33% | 0.120 | no |
| 1h | funding_tertile | LOW | 6 | 0.000388 | -0.001012 | 33.33% | 0.549 | no |
| 1h | funding_tertile | MID | 5 | -0.002307 | -0.003707 | 0.00% | 0.000 | no |
| 4h | overall | ALL | 17 | 0.000576 | -0.000824 | 58.82% | 0.806 | no |
| 4h | taker_buy_ratio_tertile | HIGH | 6 | 0.003015 | 0.001615 | 50.00% | 1.594 | no |
| 4h | taker_buy_ratio_tertile | LOW | 6 | 0.003959 | 0.002559 | 83.33% | 2.840 | no |
| 4h | taker_buy_ratio_tertile | MID | 5 | -0.006411 | -0.007811 | 40.00% | 0.178 | no |
| 4h | oi_change_tertile | HIGH | 6 | 0.004955 | 0.003555 | 66.67% | 2.297 | no |
| 4h | oi_change_tertile | LOW | 6 | -0.006056 | -0.007456 | 33.33% | 0.191 | no |
| 4h | oi_change_tertile | MID | 5 | 0.003279 | 0.001879 | 80.00% | 22.369 | no |
| 4h | volatility_tertile | HIGH | 6 | -0.004217 | -0.005617 | 50.00% | 0.322 | no |
| 4h | volatility_tertile | LOW | 6 | 0.006294 | 0.004894 | 83.33% | 3.852 | no |
| 4h | volatility_tertile | MID | 5 | -0.000536 | -0.001936 | 40.00% | 0.205 | no |
| 4h | funding_tertile | HIGH | 6 | 0.005217 | 0.003817 | 66.67% | 2.392 | no |
| 4h | funding_tertile | LOW | 6 | -0.002960 | -0.004360 | 66.67% | 0.327 | no |
| 4h | funding_tertile | MID | 5 | -0.000751 | -0.002151 | 40.00% | 0.363 | no |

## 预先声明的 2025 验证门槛

- 条件：BTCUSDT、ETHUSDT 均在 4h 总体桶达到样本数 >= 200、平均成本后收益 > 0、Profit Factor >= 1.15。
- 结果：`未通过；不得进入候选策略或回测调参`。
- 任一细分桶样本不足 200 时仅作描述，不形成策略结论。
