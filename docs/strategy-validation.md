# Strategy Validation

- Symbol: `ETH/USDT`
- Timeframe: `5m`
- Annual window: `365` days
- Rolling windows: `12` non-overlapping `30`-day windows

未通过验证的模式保持不可用于未来自动化 testnet 执行；只有状态为 `通过` 的模式可进入后续自动化模拟盘流程。

| Mode | Margin | Status | Avg 30d Return % | Worst 30d Return % | Annual Return % | Max Drawdown % | Profit Factor | Annual Trades | Reasons |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| KEY_LEVEL | ISOLATED | 未通过验证 | -17.04 | -19.21 | -90.04 | -90.04 | 0.43 | 1505 | 平均窗口收益不为正；全年收益不为正；最大回撤达到或超过 30%；Profit Factor 低于 1.05 |
| KEY_LEVEL | CROSS | 未通过验证 | -17.04 | -19.21 | -90.04 | -90.04 | 0.43 | 1505 | 平均窗口收益不为正；全年收益不为正；最大回撤达到或超过 30%；Profit Factor 低于 1.05 |
| RSI_REVERSAL | ISOLATED | 未通过验证 | -0.24 | -0.47 | -3.06 | -3.30 | 0.39 | 49 | 平均窗口收益不为正；全年收益不为正；Profit Factor 低于 1.05；年化交易次数少于 50 |
| RSI_REVERSAL | CROSS | 未通过验证 | -0.24 | -0.47 | -3.06 | -3.30 | 0.39 | 49 | 平均窗口收益不为正；全年收益不为正；Profit Factor 低于 1.05；年化交易次数少于 50 |
| KEY_LEVEL_RSI | ISOLATED | 未通过验证 | -17.11 | -19.57 | -90.05 | -90.06 | 0.43 | 1507 | 平均窗口收益不为正；全年收益不为正；最大回撤达到或超过 30%；Profit Factor 低于 1.05 |
| KEY_LEVEL_RSI | CROSS | 未通过验证 | -17.11 | -19.57 | -90.05 | -90.06 | 0.43 | 1507 | 平均窗口收益不为正；全年收益不为正；最大回撤达到或超过 30%；Profit Factor 低于 1.05 |
