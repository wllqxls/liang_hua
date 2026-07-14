# Key-Level Event Factor Research Design

## Purpose and boundary

This research answers a narrower question than a strategy backtest: after a
key-level breach event, which *known-at-close* features are associated with a
better future directional return? It creates no signals, orders, positions, or
strategy entry points.

## Event and features

An event is a single closed entry candle that breaches exactly one prior
20-candle key level:

- `BUY`: low is below the prior 20-candle low.
- `SELL`: high is above the prior 20-candle high.
- A candle breaching both sides is ambiguous and excluded.

The event row freezes direction, breached level, breach distance in ATR, candle
body in ATR, ATR as a percentage of close, RSI, volume divided by the *prior*
20-candle mean volume, 1h environment, and 4h label. Context joins use only
context candles already closed at the event close.

## Labels and cost

Labels are future directional close-to-close returns. They are explicitly
separate from event features:

| Entry timeframe | Labels |
|---|---|
| `5m` | 5m, 15m, 1h, 4h |
| `15m` | 15m, 1h, 4h |

Every label subtracts fixed round-trip taker plus slippage cost of `0.0014`.
It does not include funding because the longest horizon is four hours.

## Analysis rule

The report groups the one-hour label by direction, 4h label, volume tertile,
and volatility tertile. A bucket requires at least 200 events. A positive
average cost-after return is evidence only for a *factor hypothesis*; it is not
a trading rule. Any candidate proposed later must be frozen and independently
validated under the project strategy gates.
