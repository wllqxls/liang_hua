# Strategy Validation

- Symbol: `ETH/USDT`
- Timeframe: `5m`
- Annual window: `365` days
- Rolling windows: `12` non-overlapping `30`-day windows

未通过验证的模式保持不可用于未来自动化 testnet 执行；只有状态为 `通过` 的模式可进入后续自动化模拟盘流程。

| Mode | Margin | Status | Avg 30d Return % | Worst 30d Return % | Annual Return % | Max Drawdown % | Profit Factor | Annual Trades | Reasons |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| KEY_LEVEL | ISOLATED | 未通过验证 | -16.83 | -24.38 | -90.05 | -90.05 | 0.44 | 1527 | 平均窗口收益不为正；全年收益不为正；最大回撤不小于 30%；Profit Factor 低于 1.05 |
| KEY_LEVEL | CROSS | 未通过验证 | -16.83 | -24.38 | -90.05 | -90.05 | 0.44 | 1527 | 平均窗口收益不为正；全年收益不为正；最大回撤不小于 30%；Profit Factor 低于 1.05 |
| RSI_REVERSAL | ISOLATED | 未通过验证 | -0.27 | -0.78 | -3.18 | -3.30 | 0.36 | 48 | 平均窗口收益不为正；全年收益不为正；Profit Factor 低于 1.05；年化交易次数少于 50 |
| RSI_REVERSAL | CROSS | 未通过验证 | -0.27 | -0.78 | -3.18 | -3.30 | 0.36 | 48 | 平均窗口收益不为正；全年收益不为正；Profit Factor 低于 1.05；年化交易次数少于 50 |
| KEY_LEVEL_RSI | ISOLATED | 未通过验证 | -16.91 | -24.74 | -90.03 | -90.03 | 0.44 | 1523 | 平均窗口收益不为正；全年收益不为正；最大回撤不小于 30%；Profit Factor 低于 1.05 |
| KEY_LEVEL_RSI | CROSS | 未通过验证 | -16.91 | -24.74 | -90.03 | -90.03 | 0.44 | 1523 | 平均窗口收益不为正；全年收益不为正；最大回撤不小于 30%；Profit Factor 低于 1.05 |
