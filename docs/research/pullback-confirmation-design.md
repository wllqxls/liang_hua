# PULLBACK_CONFIRMATION Research Design

## Scope

This is a research-only candidate. It may be executed through the research
runner, but it must not be exposed as a web strategy, optimization candidate,
testnet strategy, or live-trading strategy.

## Fixed event state machine

The machine keeps one state across consecutive closed entry candles:

1. `READY`: a buy event starts when the candle breaches the previous 20-candle
   low; a sell event starts when it breaches the previous 20-candle high. The
   breached level and that candle's ATR are frozen. No entry occurs on this
   event candle.
2. `WAIT_CONFIRMATION`: evaluate at most the next three closed entry candles.
   A buy confirms only when a later bullish candle closes above the frozen
   level. A sell confirms only when a later bearish candle closes below the
   frozen level.
3. `INVALID`: a buy event fails when a later low falls 0.8 ATR below its frozen
   level; a sell event fails when a later high rises 0.8 ATR above its frozen
   level. Events also fail after the third unconfirmed candle.
4. `ENTERED`: confirmation emits exactly one signal. The simulator fills it on
   the next candle open using its existing adverse-slippage model.
5. `RESET_REQUIRED`: after confirmation, invalidation, or expiry, the machine
   will not create another event until price first moves at least 1.0 frozen ATR
   away from that event level in the favourable direction. It then returns to
   `READY`; a later breach is a new event.

All transitions are calculated from the snapshot being processed. The machine
never reads a future candle, and confirmation cannot happen on the event candle.

## Fixed research presets

The first experiment has no parameter search. It runs these two predeclared
4-hour context presets:

| Preset | Rule |
|---|---|
| `OFF` | Do not filter a confirmed event by 4h context. |
| `ALIGN` | Buy only with `FILTER_LONG`; sell only with `FILTER_SHORT`. |

Risk distances are frozen at `0.8 ATR` stop and `1.5 ATR` target. The existing
validation taker fee (`0.0005`), slippage (`0.0002`), and 8-hour funding rate
(`0.0001`) remain mandatory.

## Research matrix and promotion gate

Run both `5m` and `15m`, both BTC/USDT and ETH/USDT, both presets, 12
non-overlapping 30-day windows, and separate 2025 and 2026 annual slices. A
time range selected only after the rule is frozen is retained as the final
holdout and must not be used to revise the machine.

Promotion requires every existing automatic gate plus cost-after PF >= 1.15,
at least 8 positive independent windows, positive post-cost results in both
years, cross-symbol support, and a passing holdout. Failure produces a research
report and ends the candidate; it does not authorize parameter tuning.

## First research decision

**REJECTED — 2026-07-14.** The fixed first candidate failed all four completed
2025 ETH/USDT slices. Its annual cost-after return was negative in every
combination, Profit Factor ranged from 0.50 to 0.73, and only 2 or 3 of 12
independent windows were positive. The detailed rows are recorded in
`pullback-confirmation-report.md`.

BTC/USDT files are absent locally and the available 2026 ETH/USDT history ends
on 2026-07-11, so neither can supply the required full annual validation. Those
gaps cannot rescue a candidate that already fails the completed discovery
slices; no parameter search or promotion is permitted.
