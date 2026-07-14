# PULLBACK_CONFIRMATION Research Report

## Decision

**Rejected.** `PULLBACK_CONFIRMATION` remains a research artifact and must not
be promoted to a Web entry mode, optimizer candidate, testnet strategy, or live
strategy. The fixed machine failed its first complete discovery set, so the
research protocol forbids parameter tuning.

## Fixed conditions

- Symbol: `ETH/USDT`
- Year: `2025`
- Costs: taker `0.0005`, slippage `0.0002`, funding `0.0001` every 8 hours
- Entry timeframes: `5m`, `15m`
- 4h presets: `OFF`, `ALIGN`
- Windows: 12 non-overlapping 30-day windows plus one 365-day slice
- State machine and thresholds: `pullback-confirmation-design.md`

| Timeframe | 4h preset | Avg 30d return % | Positive windows | Annual return % | Max drawdown % | Cost-after PF | Trades | Result |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 5m | OFF | -0.86 | 2 / 12 | -3.36 | -3.97 | 0.55 | 57 | Rejected |
| 5m | ALIGN | -0.58 | 2 / 12 | -1.10 | -1.67 | 0.73 | 33 | Rejected |
| 15m | OFF | -0.60 | 3 / 12 | -3.46 | -4.21 | 0.60 | 44 | Rejected |
| 15m | ALIGN | -0.30 | 3 / 12 | -2.36 | -3.49 | 0.50 | 26 | Rejected |

None reached even the base requirements of positive average and annual return,
PF >= 1.05, and 50 annual trades. None approached the candidate gates of PF >=
1.15 and at least 8 positive windows.

## Matrix availability

- `BTC/USDT`: no local 2025 or 2026 data files.
- `ETH/USDT` 2026: available data ends on 2026-07-11, short of a full 365-day
  annual slice.

These missing slices prevent cross-symbol and 2026 confirmation. They do not
justify adjusting this rejected candidate; the next research proposal must be
a different, separately documented hypothesis.
