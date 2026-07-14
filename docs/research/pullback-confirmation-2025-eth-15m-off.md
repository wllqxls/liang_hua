# PULLBACK_CONFIRMATION Research Report

- Candidate status: research only; not eligible for web, testnet, or live use.
- Costs: taker 0.0005, slippage 0.0002, funding 0.0001 per 8 hours.
- State machine and promotion rules: `docs/research/pullback-confirmation-design.md`.

| Symbol | Timeframe | Year | 4h Preset | Status | Avg 30d % | Positive Windows | Annual % | Max DD % | PF | Trades | Reasons |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| ETH/USDT | 15m | 2025 | OFF | FAIL_SLICE | -0.60 | 3 | -3.46 | -4.21 | 0.60 | 44 | 平均窗口收益不为正; 全年收益不为正; Profit Factor 低于 1.05; 年化交易次数少于 50; cost-after Profit Factor is below 1.15; fewer than 8 of 12 independent windows are positive |
