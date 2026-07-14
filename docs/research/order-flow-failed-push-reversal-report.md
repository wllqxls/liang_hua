# 主动资金推高后的回调反转研究报告

- 状态：只读因子研究；不是策略回测、模拟盘或实盘建议。
- 设计：`docs/research/order-flow-failed-push-reversal-design.md`。
- 数据：2024 用于实现和描述，2025 是独立验证；2026 未读取。
- 成本：完整往返 `0.0014`；30m 是唯一主检验窗口。
- 代码版本：`63800ec`。

## 事件与数据排除

| 标的 | 年份 | 冷却后事件数 | 冷却前合格行 | 因 OI 缺口排除行 | 事件 CSV |
|---|---:|---:|---:|---:|---|
| BTCUSDT | 2024 | 1 | 1 | 129 | `results\research\order_flow\BTCUSDT_15m_2024_failed_push_reversal.csv` |
| ETHUSDT | 2024 | 3 | 3 | 129 | `results\research\order_flow\ETHUSDT_15m_2024_failed_push_reversal.csv` |
| BTCUSDT | 2025 | 3 | 3 | 130 | `results\research\order_flow\BTCUSDT_15m_2025_failed_push_reversal.csv` |
| ETHUSDT | 2025 | 5 | 5 | 130 | `results\research\order_flow\ETHUSDT_15m_2025_failed_push_reversal.csv` |
## BTCUSDT 2024

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 30m | overall | ALL | 1 | 0.001492 | 0.000092 | 100.00% | ∞ | no |
| 30m | taker_buy_ratio_tertile | LOW | 1 | 0.001492 | 0.000092 | 100.00% | ∞ | no |
| 30m | oi_change_tertile | UNAVAILABLE | 1 | 0.001492 | 0.000092 | 100.00% | ∞ | no |
| 30m | volatility_tertile | LOW | 1 | 0.001492 | 0.000092 | 100.00% | ∞ | no |
| 30m | funding_tertile | LOW | 1 | 0.001492 | 0.000092 | 100.00% | ∞ | no |
| 1h | overall | ALL | 1 | -0.003616 | -0.005016 | 0.00% | 0.000 | no |
| 1h | taker_buy_ratio_tertile | LOW | 1 | -0.003616 | -0.005016 | 0.00% | 0.000 | no |
| 1h | oi_change_tertile | UNAVAILABLE | 1 | -0.003616 | -0.005016 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | LOW | 1 | -0.003616 | -0.005016 | 0.00% | 0.000 | no |
| 1h | funding_tertile | LOW | 1 | -0.003616 | -0.005016 | 0.00% | 0.000 | no |

## ETHUSDT 2024

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 30m | overall | ALL | 3 | -0.002279 | -0.003679 | 0.00% | 0.000 | no |
| 30m | taker_buy_ratio_tertile | HIGH | 1 | -0.003320 | -0.004720 | 0.00% | 0.000 | no |
| 30m | taker_buy_ratio_tertile | LOW | 1 | -0.000540 | -0.001940 | 0.00% | 0.000 | no |
| 30m | taker_buy_ratio_tertile | MID | 1 | -0.002976 | -0.004376 | 0.00% | 0.000 | no |
| 30m | oi_change_tertile | HIGH | 1 | -0.000540 | -0.001940 | 0.00% | 0.000 | no |
| 30m | oi_change_tertile | LOW | 1 | -0.003320 | -0.004720 | 0.00% | 0.000 | no |
| 30m | oi_change_tertile | MID | 1 | -0.002976 | -0.004376 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | HIGH | 1 | -0.002976 | -0.004376 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | LOW | 1 | -0.003320 | -0.004720 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | MID | 1 | -0.000540 | -0.001940 | 0.00% | 0.000 | no |
| 30m | funding_tertile | HIGH | 1 | -0.002976 | -0.004376 | 0.00% | 0.000 | no |
| 30m | funding_tertile | LOW | 1 | -0.000540 | -0.001940 | 0.00% | 0.000 | no |
| 30m | funding_tertile | MID | 1 | -0.003320 | -0.004720 | 0.00% | 0.000 | no |
| 1h | overall | ALL | 3 | 0.000380 | -0.001020 | 33.33% | 0.658 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 1 | -0.004147 | -0.005547 | 0.00% | 0.000 | no |
| 1h | taker_buy_ratio_tertile | LOW | 1 | -0.002004 | -0.003404 | 0.00% | 0.000 | no |
| 1h | taker_buy_ratio_tertile | MID | 1 | 0.007292 | 0.005892 | 100.00% | ∞ | no |
| 1h | oi_change_tertile | HIGH | 1 | -0.002004 | -0.003404 | 0.00% | 0.000 | no |
| 1h | oi_change_tertile | LOW | 1 | -0.004147 | -0.005547 | 0.00% | 0.000 | no |
| 1h | oi_change_tertile | MID | 1 | 0.007292 | 0.005892 | 100.00% | ∞ | no |
| 1h | volatility_tertile | HIGH | 1 | 0.007292 | 0.005892 | 100.00% | ∞ | no |
| 1h | volatility_tertile | LOW | 1 | -0.004147 | -0.005547 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | MID | 1 | -0.002004 | -0.003404 | 0.00% | 0.000 | no |
| 1h | funding_tertile | HIGH | 1 | 0.007292 | 0.005892 | 100.00% | ∞ | no |
| 1h | funding_tertile | LOW | 1 | -0.002004 | -0.003404 | 0.00% | 0.000 | no |
| 1h | funding_tertile | MID | 1 | -0.004147 | -0.005547 | 0.00% | 0.000 | no |

## BTCUSDT 2025

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 30m | overall | ALL | 3 | -0.001116 | -0.002516 | 0.00% | 0.000 | no |
| 30m | taker_buy_ratio_tertile | HIGH | 1 | -0.000226 | -0.001626 | 0.00% | 0.000 | no |
| 30m | taker_buy_ratio_tertile | LOW | 1 | -0.002336 | -0.003736 | 0.00% | 0.000 | no |
| 30m | taker_buy_ratio_tertile | MID | 1 | -0.000785 | -0.002185 | 0.00% | 0.000 | no |
| 30m | oi_change_tertile | HIGH | 1 | -0.002336 | -0.003736 | 0.00% | 0.000 | no |
| 30m | oi_change_tertile | LOW | 1 | -0.000785 | -0.002185 | 0.00% | 0.000 | no |
| 30m | oi_change_tertile | MID | 1 | -0.000226 | -0.001626 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | HIGH | 1 | -0.002336 | -0.003736 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | LOW | 1 | -0.000785 | -0.002185 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | MID | 1 | -0.000226 | -0.001626 | 0.00% | 0.000 | no |
| 30m | funding_tertile | HIGH | 1 | -0.000785 | -0.002185 | 0.00% | 0.000 | no |
| 30m | funding_tertile | LOW | 1 | -0.002336 | -0.003736 | 0.00% | 0.000 | no |
| 30m | funding_tertile | MID | 1 | -0.000226 | -0.001626 | 0.00% | 0.000 | no |
| 1h | overall | ALL | 3 | -0.000736 | -0.002136 | 66.67% | 0.217 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 1 | 0.002281 | 0.000881 | 100.00% | ∞ | no |
| 1h | taker_buy_ratio_tertile | LOW | 1 | 0.002299 | 0.000899 | 100.00% | ∞ | no |
| 1h | taker_buy_ratio_tertile | MID | 1 | -0.006789 | -0.008189 | 0.00% | 0.000 | no |
| 1h | oi_change_tertile | HIGH | 1 | 0.002299 | 0.000899 | 100.00% | ∞ | no |
| 1h | oi_change_tertile | LOW | 1 | -0.006789 | -0.008189 | 0.00% | 0.000 | no |
| 1h | oi_change_tertile | MID | 1 | 0.002281 | 0.000881 | 100.00% | ∞ | no |
| 1h | volatility_tertile | HIGH | 1 | 0.002299 | 0.000899 | 100.00% | ∞ | no |
| 1h | volatility_tertile | LOW | 1 | -0.006789 | -0.008189 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | MID | 1 | 0.002281 | 0.000881 | 100.00% | ∞ | no |
| 1h | funding_tertile | HIGH | 1 | -0.006789 | -0.008189 | 0.00% | 0.000 | no |
| 1h | funding_tertile | LOW | 1 | 0.002299 | 0.000899 | 100.00% | ∞ | no |
| 1h | funding_tertile | MID | 1 | 0.002281 | 0.000881 | 100.00% | ∞ | no |

## ETHUSDT 2025

| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 30m | overall | ALL | 5 | -0.000422 | -0.001822 | 20.00% | 0.038 | no |
| 30m | taker_buy_ratio_tertile | HIGH | 2 | -0.001084 | -0.002484 | 0.00% | 0.000 | no |
| 30m | taker_buy_ratio_tertile | LOW | 2 | 0.000203 | -0.001197 | 50.00% | 0.130 | no |
| 30m | taker_buy_ratio_tertile | MID | 1 | -0.000345 | -0.001745 | 0.00% | 0.000 | no |
| 30m | oi_change_tertile | HIGH | 2 | -0.000814 | -0.002214 | 0.00% | 0.000 | no |
| 30m | oi_change_tertile | LOW | 2 | 0.000203 | -0.001197 | 50.00% | 0.130 | no |
| 30m | oi_change_tertile | MID | 1 | -0.000885 | -0.002285 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | HIGH | 2 | -0.001084 | -0.002484 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | LOW | 2 | -0.000849 | -0.002249 | 0.00% | 0.000 | no |
| 30m | volatility_tertile | MID | 1 | 0.001758 | 0.000358 | 100.00% | ∞ | no |
| 30m | funding_tertile | HIGH | 2 | -0.001318 | -0.002718 | 0.00% | 0.000 | no |
| 30m | funding_tertile | LOW | 2 | -0.000615 | -0.002015 | 0.00% | 0.000 | no |
| 30m | funding_tertile | MID | 1 | 0.001758 | 0.000358 | 100.00% | ∞ | no |
| 1h | overall | ALL | 5 | -0.000706 | -0.002106 | 20.00% | 0.036 | no |
| 1h | taker_buy_ratio_tertile | HIGH | 2 | -0.002414 | -0.003814 | 0.00% | 0.000 | no |
| 1h | taker_buy_ratio_tertile | LOW | 2 | 0.000878 | -0.000522 | 50.00% | 0.276 | no |
| 1h | taker_buy_ratio_tertile | MID | 1 | -0.000456 | -0.001856 | 0.00% | 0.000 | no |
| 1h | oi_change_tertile | HIGH | 2 | -0.001222 | -0.002622 | 0.00% | 0.000 | no |
| 1h | oi_change_tertile | LOW | 2 | 0.000878 | -0.000522 | 50.00% | 0.276 | no |
| 1h | oi_change_tertile | MID | 1 | -0.002841 | -0.004241 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | HIGH | 2 | -0.002414 | -0.003814 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | LOW | 2 | -0.000250 | -0.001650 | 0.00% | 0.000 | no |
| 1h | volatility_tertile | MID | 1 | 0.001799 | 0.000399 | 100.00% | ∞ | no |
| 1h | funding_tertile | HIGH | 2 | -0.001016 | -0.002416 | 0.00% | 0.000 | no |
| 1h | funding_tertile | LOW | 2 | -0.001648 | -0.003048 | 0.00% | 0.000 | no |
| 1h | funding_tertile | MID | 1 | 0.001799 | 0.000399 | 100.00% | ∞ | no |

## 预先声明的 2025 验证门槛

- 条件：BTCUSDT、ETHUSDT 均在 30m 总体桶达到样本数 >= 200、平均成本后收益 > 0、Profit Factor >= 1.15。
- 结果：`未通过；不得进入候选策略或回测调参`。
- 任一细分桶样本不足 200 时仅作描述，不形成策略结论。
