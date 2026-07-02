# Strategy Module Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four legacy entry strategies with a shared closed-candle signal pipeline for key-level reversal, RSI reversal, and key-level-first dual mode, including fixed ATR trade plans, isolated/cross margin simulation, updated optimization, and the approved frontend.

**Architecture:** Pure indicator and signal modules consume aligned `5m/15m`, closed `1h`, and closed `4h` candles. A deterministic dispatcher emits at most one immutable signal, and a dedicated event-driven simulator fills it at the next candle open before creating a fixed-ATR trade plan; web and optimizer layers consume the same mode identifiers and result types.

**Tech Stack:** Python 3.11+, pandas, numpy, FastAPI, Pydantic, vanilla JavaScript, pytest

---

## File map

**Create:**

- `src/strategies/indicators.py` — Wilder RSI/ATR, EMA, and Bollinger calculations.
- `src/strategies/signal_models.py` — stable enums and immutable market/signal/trade-plan records.
- `src/strategies/market_context.py` — closed-candle cross-timeframe alignment and snapshots.
- `src/strategies/signal_evaluators.py` — pure RSI and key-level evaluators.
- `src/strategies/signal_dispatcher.py` — three-mode priority routing.
- `src/backtest/signal_simulator.py` — next-open fills, fixed exits, fees, funding, margin, and equity accounting.
- `scripts/validate_strategies.py` — reproducible 12-window and full-year validation report generator.
- `tests/test_indicators.py` — fixed numerical indicator contracts.
- `tests/test_signal_context.py` — closed-candle alignment and no-look-ahead contracts.
- `tests/test_signal_evaluators.py` — exact entry and rejection rules.
- `tests/test_signal_dispatcher.py` — mode and priority contracts.
- `tests/test_signal_simulator.py` — fill, ATR freeze, margin, and state contracts.
- `tests/test_validation_script.py` — threshold and report-label contracts.

**Modify:**

- `src/backtest/engine.py` — route new modes through the simulator and expose enriched trades.
- `src/backtest/optimizer.py` — search only approved modes and entry timeframes; remove exit-amount dimensions.
- `src/web/schemas.py` — replace legacy strategy/risk request fields with mode, margin mode, and opening amount.
- `src/web/routes.py` — register modes, validate required data, call the new engine, and reshape optimizer output.
- `templates/backtest.html` — mode selector, approved row layout, and enriched trade table.
- `static/js/backtest.js` — new payload, validation, optimizer apply behavior, and rendering.
- `tests/test_engine.py`, `tests/test_optimizer.py`, `tests/test_routes.py`, `tests/test_search_jobs.py`, `tests/test_styles.py`, `tests/test_strategies.py` — replace legacy contracts without deleting test files.
- `README.md`, `CLAUDE.md`, `AGENTS.md` — document the new modes, timeframes, commands, and simulator boundary after code is verified.

Legacy files `src/strategies/sr_breakout.py`, `ma_cross.py`, `rsi_reversion.py`, and `key_level_scoring.py` are not deleted. They leave the route/optimizer registries, and `ma_cross.py` is no longer called as an entry strategy.

---

### Task 1: Lock the indicator formulas

**Files:**
- Create: `src/strategies/indicators.py`
- Create: `tests/test_indicators.py`

- [ ] **Step 1: Write fixed-sample failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from src.strategies.indicators import atr_wilder, bollinger_bands, ema, rsi_wilder


def test_indicator_contracts_use_approved_formulas() -> None:
    close = pd.Series([100 + i for i in range(20)] + [118, 116, 119, 117, 121], dtype=float)
    high = close + 2
    low = close - 2

    expected_ema = close.ewm(span=20, adjust=False, min_periods=20).mean()
    assert ema(close, 20).equals(expected_ema)

    middle, upper, lower = bollinger_bands(close, window=20, deviations=2)
    expected_middle = close.rolling(20).mean()
    expected_std = close.rolling(20).std(ddof=0)
    pd.testing.assert_series_equal(middle, expected_middle)
    pd.testing.assert_series_equal(upper, expected_middle + expected_std * 2)
    pd.testing.assert_series_equal(lower, expected_middle - expected_std * 2)

    rsi = rsi_wilder(close, 14)
    atr = atr_wilder(high, low, close, 14)
    assert np.isfinite(rsi.iloc[-1])
    assert np.isfinite(atr.iloc[-1])
    assert rsi.iloc[-1] == pytest.approx(79.4564428889596)
    assert atr.iloc[-1] == pytest.approx(4.204446064139942)
    assert rsi.iloc[:14].isna().all()
    assert atr.iloc[:14].isna().all()
```

- [ ] **Step 2: Run the test and verify the module is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_indicators.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: src.strategies.indicators`.

- [ ] **Step 3: Implement pure pandas/numpy indicators**

```python
from __future__ import annotations

import pandas as pd


def ema(values: pd.Series, window: int) -> pd.Series:
    return values.astype(float).ewm(span=window, adjust=False, min_periods=window).mean()


def _wilder(values: pd.Series, window: int) -> pd.Series:
    result = pd.Series(float('nan'), index=values.index, dtype=float)
    if len(values) <= window:
        return result
    seed = values.iloc[1:window + 1].mean()
    result.iloc[window] = seed
    for index in range(window + 1, len(values)):
        result.iloc[index] = (result.iloc[index - 1] * (window - 1) + values.iloc[index]) / window
    return result


def rsi_wilder(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.astype(float).diff()
    average_gain = _wilder(delta.clip(lower=0), window)
    average_loss = _wilder(-delta.clip(upper=0), window)
    relative_strength = average_gain / average_loss.where(average_loss != 0)
    rsi = 100 - 100 / (1 + relative_strength)
    return rsi.mask((average_loss == 0) & (average_gain > 0), 100).mask(
        (average_loss == 0) & (average_gain == 0), 50
    )


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    previous_close = close.astype(float).shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    return _wilder(true_range, window)


def bollinger_bands(
    close: pd.Series, window: int = 20, deviations: float = 2
) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = close.astype(float).rolling(window).mean()
    standard_deviation = close.astype(float).rolling(window).std(ddof=0)
    return middle, middle + standard_deviation * deviations, middle - standard_deviation * deviations
```

- [ ] **Step 4: Run indicator tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_indicators.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the indicator unit**

```powershell
git add src/strategies/indicators.py tests/test_indicators.py
git commit -m "Add stable trading indicator formulas"
```

---

### Task 2: Define immutable signal contracts and closed-candle context

**Files:**
- Create: `src/strategies/signal_models.py`
- Create: `src/strategies/market_context.py`
- Create: `tests/test_signal_context.py`

- [ ] **Step 1: Write failing context tests**

```python
from datetime import datetime, timezone

import pandas as pd

from src.strategies.market_context import build_market_snapshots


def _candles(index: pd.DatetimeIndex, closes: list[float]) -> pd.DataFrame:
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame({
        'Open': close,
        'High': close + 1,
        'Low': close - 1,
        'Close': close,
        'Volume': 100.0,
    })


def test_snapshot_never_reads_unclosed_hour_or_four_hour_bar() -> None:
    entry_index = pd.date_range('2026-01-01', periods=300, freq='5min', tz='UTC')
    hour_index = pd.date_range('2025-12-31', periods=30, freq='1h', tz='UTC')
    four_hour_index = pd.date_range('2025-12-28', periods=40, freq='4h', tz='UTC')
    entry = _candles(entry_index, list(range(100, 400)))
    hour = _candles(hour_index, list(range(100, 130)))
    four_hour = _candles(four_hour_index, list(range(100, 140)))

    snapshots = build_market_snapshots(entry, hour, four_hour, timeframe='5m')

    at_0100 = snapshots.loc[pd.Timestamp('2026-01-01 01:00', tz='UTC')]
    assert at_0100.context_1h_closed_at <= pd.Timestamp('2026-01-01 01:00', tz='UTC')
    assert at_0100.context_4h_closed_at <= pd.Timestamp('2026-01-01 01:00', tz='UTC')
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_signal_context.py -q`

Expected: FAIL because the new models and builder do not exist.

- [ ] **Step 3: Add stable enums and records**

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import pandas as pd


class SignalMode(StrEnum):
    KEY_LEVEL = 'KEY_LEVEL'
    RSI_REVERSAL = 'RSI_REVERSAL'
    KEY_LEVEL_RSI = 'KEY_LEVEL_RSI'


class MarginMode(StrEnum):
    ISOLATED = 'ISOLATED'
    CROSS = 'CROSS'


class FilterLabel(StrEnum):
    LONG = 'FILTER_LONG'
    SHORT = 'FILTER_SHORT'
    NEUTRAL = 'FILTER_NEUTRAL'


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    closed_at: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    atr: float
    rsi: float
    bollinger_upper: float
    bollinger_lower: float
    previous_high_20: float
    previous_low_20: float
    environment_side: Literal['BUY', 'SELL'] | None
    filter_label: FilterLabel
    context_1h_closed_at: pd.Timestamp
    context_4h_closed_at: pd.Timestamp


@dataclass(frozen=True, slots=True)
class Signal:
    mode: SignalMode
    strategy: str
    side: Literal['BUY', 'SELL']
    signal_time: pd.Timestamp
    signal_close: float
    atr_snapshot: float
    stop_atr_multiple: float
    target_atr_multiple: float
    stop_distance: float
    target_distance: float
    estimated_stop_price: float
    estimated_target_price: float
    environment_side: Literal['BUY', 'SELL']
    filter_label: FilterLabel
    reason: str
    score: int
```

- [ ] **Step 4: Implement as-of context construction**

In `market_context.py`, calculate entry indicators first. Shift the `1h` and `4h` feature timestamps forward by their full candle durations before `pd.merge_asof`, so a bar is visible only after it has closed. Build `environment_side` from `1h Close` versus EMA20 and `FilterLabel` from `4h EMA10` versus EMA30. Use `.rolling(20).max().shift(1)` and `.min().shift(1)` for key levels.

```python
def _closed_features(frame: pd.DataFrame, duration: pd.Timedelta) -> pd.DataFrame:
    result = frame.copy()
    result['closed_at'] = result.index + duration
    return result.set_index('closed_at')


def _asof(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    return pd.merge_asof(
        left.sort_index(), right.sort_index(), left_index=True, right_index=True, direction='backward'
    )
```

- [ ] **Step 5: Run context and indicator tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_indicators.py tests/test_signal_context.py -q`

Expected: PASS with no context value taken before its `closed_at` timestamp.

- [ ] **Step 6: Commit the context unit**

```powershell
git add src/strategies/signal_models.py src/strategies/market_context.py tests/test_signal_context.py
git commit -m "Add closed candle market snapshots"
```

---

### Task 3: Implement the two pure signal evaluators

**Files:**
- Create: `src/strategies/signal_evaluators.py`
- Create: `tests/test_signal_evaluators.py`

- [ ] **Step 1: Write failing exact-rule tests**

```python
from dataclasses import replace
import pandas as pd

from src.strategies.signal_evaluators import evaluate_key_level, evaluate_rsi_reversal
from src.strategies.signal_models import FilterLabel, MarketSnapshot, SignalMode


BASE = MarketSnapshot(
    closed_at=pd.Timestamp('2026-01-01 00:05', tz='UTC'), open=100, high=101, low=99, close=100,
    atr=10, rsi=50, bollinger_upper=110, bollinger_lower=90,
    previous_high_20=105, previous_low_20=95, environment_side='BUY',
    filter_label=FilterLabel.SHORT,
    context_1h_closed_at=pd.Timestamp('2026-01-01 00:00', tz='UTC'),
    context_4h_closed_at=pd.Timestamp('2026-01-01 00:00', tz='UTC'),
)


def test_rsi_long_requires_oversold_touch_reclaim_and_long_environment() -> None:
    signal = evaluate_rsi_reversal(
        replace(BASE, rsi=24.9, low=89, close=91), SignalMode.RSI_REVERSAL
    )
    assert signal is not None
    assert (signal.side, signal.stop_distance, signal.target_distance) == ('BUY', 6, 12)
    assert signal.filter_label == FilterLabel.SHORT
    assert evaluate_rsi_reversal(replace(BASE, rsi=25, low=89, close=91), SignalMode.RSI_REVERSAL) is None


def test_key_level_uses_correct_false_break_directions() -> None:
    long_signal = evaluate_key_level(
        replace(BASE, low=94, close=96, environment_side='BUY'), SignalMode.KEY_LEVEL
    )
    short_signal = evaluate_key_level(
        replace(BASE, high=106, close=104, environment_side='SELL'), SignalMode.KEY_LEVEL
    )
    assert (long_signal.side, long_signal.score) == ('BUY', 8)
    assert (short_signal.side, short_signal.score) == ('SELL', 8)
    assert long_signal.stop_distance == 8
    assert long_signal.target_distance == 15
```

- [ ] **Step 2: Run tests and verify evaluator imports fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_signal_evaluators.py -q`

Expected: FAIL with missing evaluator functions.

- [ ] **Step 3: Implement a shared signal constructor and both evaluators**

```python
def _signal(
    snapshot: MarketSnapshot,
    mode: SignalMode,
    *,
    strategy: str,
    side: Literal['BUY', 'SELL'],
    stop_multiple: float,
    target_multiple: float,
    reason: str,
    score: int,
) -> Signal:
    stop_distance = snapshot.atr * stop_multiple
    target_distance = snapshot.atr * target_multiple
    sign = 1 if side == 'BUY' else -1
    return Signal(
        mode=mode, strategy=strategy, side=side, signal_time=snapshot.closed_at,
        signal_close=snapshot.close, atr_snapshot=snapshot.atr,
        stop_atr_multiple=stop_multiple, target_atr_multiple=target_multiple,
        stop_distance=stop_distance, target_distance=target_distance,
        estimated_stop_price=snapshot.close - sign * stop_distance,
        estimated_target_price=snapshot.close + sign * target_distance,
        environment_side=side, filter_label=snapshot.filter_label,
        reason=reason, score=score,
    )
```

Return no signal for non-finite indicators, missing environment, boundary equality (`RSI == 25/75`), incomplete Bollinger reclaim, incomplete false break, or environment mismatch. Do not consult the `4h` label when deciding.

- [ ] **Step 4: Run evaluator tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_signal_evaluators.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the evaluator unit**

```powershell
git add src/strategies/signal_evaluators.py tests/test_signal_evaluators.py
git commit -m "Add RSI and key level signal evaluators"
```

---

### Task 4: Add deterministic mode dispatch

**Files:**
- Create: `src/strategies/signal_dispatcher.py`
- Create: `tests/test_signal_dispatcher.py`

- [ ] **Step 1: Write failing mode and priority tests**

```python
from unittest.mock import Mock

from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.signal_models import SignalMode


def test_dual_mode_prefers_key_level_and_calls_rsi_only_as_fallback(base_snapshot, buy_signal) -> None:
    key_level = Mock(return_value=buy_signal)
    rsi = Mock()
    assert dispatch_signal(base_snapshot, SignalMode.KEY_LEVEL_RSI, key_level, rsi) is buy_signal
    rsi.assert_not_called()

    key_level.return_value = None
    rsi.return_value = buy_signal
    assert dispatch_signal(base_snapshot, SignalMode.KEY_LEVEL_RSI, key_level, rsi) is buy_signal
    rsi.assert_called_once()
```

- [ ] **Step 2: Run and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_signal_dispatcher.py -q`

Expected: FAIL because `dispatch_signal` does not exist.

- [ ] **Step 3: Implement the three explicit branches**

```python
def dispatch_signal(snapshot, mode, key_level=evaluate_key_level, rsi=evaluate_rsi_reversal):
    if mode is SignalMode.KEY_LEVEL:
        return key_level(snapshot, mode)
    if mode is SignalMode.RSI_REVERSAL:
        return rsi(snapshot, mode)
    signal = key_level(snapshot, mode)
    return signal if signal is not None else rsi(snapshot, mode)
```

- [ ] **Step 4: Run dispatcher and evaluator tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_signal_dispatcher.py tests/test_signal_evaluators.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the dispatcher unit**

```powershell
git add src/strategies/signal_dispatcher.py tests/test_signal_dispatcher.py
git commit -m "Add prioritized signal mode dispatch"
```

---

### Task 5: Build the fixed-ATR event-driven simulator

**Files:**
- Create: `src/backtest/signal_simulator.py`
- Create: `tests/test_signal_simulator.py`
- Modify: `src/strategies/signal_models.py`

- [ ] **Step 1: Write failing trade-plan and ATR-freeze tests**

```python
from dataclasses import replace

from src.backtest.signal_simulator import build_trade_plan
from src.strategies.signal_models import MarginMode


def test_trade_plan_uses_fill_price_but_never_recalculates_signal_atr(buy_signal) -> None:
    plan = build_trade_plan(
        buy_signal, fill_price=2000, account_balance=100, opening_amount=10,
        leverage=5, margin_mode=MarginMode.ISOLATED,
    )
    assert plan.atr_snapshot == buy_signal.atr_snapshot == 10
    assert plan.stop_price == 1994
    assert plan.target_price == 2012
    assert plan.quantity == 0.025
    assert plan.expected_stop_amount == 0.15
    assert plan.expected_target_amount == 0.30
```

- [ ] **Step 2: Write failing state and margin tests**

```python
def test_pending_or_open_position_blocks_duplicate_signals(simulator, snapshots) -> None:
    result = simulator.run(snapshots)
    candle_ids = [trade.signal_time for trade in result.trades]
    assert len(candle_ids) == len(set(candle_ids))
    assert result.maximum_concurrent_positions == 1


def test_cross_margin_can_use_account_balance_but_isolated_uses_opening_margin() -> None:
    isolated = liquidation_price('BUY', 100, 5, 10, 100, MarginMode.ISOLATED, 0.005)
    cross = liquidation_price('BUY', 100, 5, 10, 100, MarginMode.CROSS, 0.005)
    assert cross < isolated
```

- [ ] **Step 3: Add `TradePlan`, `SimulationTrade`, and `SimulationResult` immutable records**

`TradePlan` stores the original `Signal`, actual fill, frozen ATR, quantity, margin mode, fixed stop/target, expected USDT outcomes, and liquidation price. `SimulationTrade` adds exit time/price/reason, fees, funding, PnL, and PnL percentage. `SimulationResult` contains trades and the equity curve.

- [ ] **Step 4: Implement `build_trade_plan`**

```python
def build_trade_plan(signal, *, fill_price, account_balance, opening_amount, leverage, margin_mode):
    notional = opening_amount * leverage
    quantity = notional / fill_price
    direction = 1 if signal.side == 'BUY' else -1
    stop_price = fill_price - direction * signal.stop_distance
    target_price = fill_price + direction * signal.target_distance
    return TradePlan(
        signal=signal, fill_price=fill_price, atr_snapshot=signal.atr_snapshot,
        quantity=quantity, opening_amount=opening_amount, notional_amount=notional,
        leverage=leverage, margin_mode=margin_mode,
        stop_price=stop_price, target_price=target_price,
        expected_stop_amount=round(quantity * signal.stop_distance, 8),
        expected_target_amount=round(quantity * signal.target_distance, 8),
        liquidation_price=liquidation_price(
            signal.side, fill_price, leverage, opening_amount, account_balance, margin_mode, 0.005
        ),
    )
```

- [ ] **Step 5: Implement the candle loop with explicit conservative ordering**

For each candle: fill the previous close's pending signal at the current open; create the trade plan before examining the candle high/low; then evaluate liquidation, stop, and target. If both stop and target are reachable in the same candle and tick order is unknown, record the stop first. If the candle opens beyond a stop, exit at the open plus configured adverse slippage. Do not close on opposite entry signals; positions exit only by stop, target, liquidation, or end-of-test finalization.

- [ ] **Step 6: Implement fees, funding, and margin semantics**

Charge taker commission on entry and exit notionals. Apply configured funding every crossed eight-hour boundary using the signed position notional. In isolated mode, liquidation collateral is `opening_amount`; in cross mode, it is current account equity. Stop simulation when equity is non-positive.

```python
def liquidation_price(side, fill_price, leverage, opening_amount, account_balance, margin_mode, rate):
    quantity = opening_amount * leverage / fill_price
    collateral = opening_amount if margin_mode is MarginMode.ISOLATED else account_balance
    if side == 'BUY':
        return max(0.0, (quantity * fill_price - collateral) / (quantity * (1 - rate)))
    return (collateral + quantity * fill_price) / (quantity * (1 + rate))


def commission(notional: float, taker_fee: float) -> float:
    return abs(notional) * taker_fee


def funding_cash_flow(side: str, notional: float, funding_rate: float) -> float:
    # Positive means cash received; at a positive funding rate longs pay and shorts receive.
    return -notional * funding_rate if side == 'BUY' else notional * funding_rate
```

- [ ] **Step 7: Run simulator tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_signal_simulator.py -q`

Expected: PASS, including same-candle stop-first behavior and no duplicate positions.

- [ ] **Step 8: Commit the simulator unit**

```powershell
git add src/backtest/signal_simulator.py src/strategies/signal_models.py tests/test_signal_simulator.py
git commit -m "Add fixed ATR signal simulator"
```

---

### Task 6: Integrate modes and enriched trades into the engine and API

**Files:**
- Modify: `src/backtest/engine.py`
- Modify: `src/web/schemas.py`
- Modify: `src/web/routes.py`
- Modify: `tests/test_engine.py`
- Modify: `tests/test_routes.py`
- Modify: `tests/test_search_jobs.py`

- [ ] **Step 1: Replace route tests with the approved request contract**

```python
def test_backtest_accepts_signal_mode_and_margin_fields(monkeypatch) -> None:
    response = client.post('/api/backtest', json={
        'symbol': 'ETH/USDT', 'timeframe': '5m', 'mode': 'KEY_LEVEL_RSI',
        'cash': 100, 'opening_amount': 10, 'margin_mode': 'ISOLATED', 'leverage': 5,
    })
    assert response.status_code == 200


def test_backtest_rejects_unsupported_entry_timeframe() -> None:
    response = client.post('/api/backtest', json={'timeframe': '1h'})
    assert response.status_code == 422
```

- [ ] **Step 2: Run route and engine tests and confirm legacy contract failures**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_engine.py tests/test_routes.py tests/test_search_jobs.py -q`

Expected: FAIL because `mode`, `opening_amount`, and `margin_mode` are not defined.

- [ ] **Step 3: Replace request fields and extend trade responses**

```python
class BacktestRequest(BaseModel):
    symbol: str = 'BTC/USDT'
    timeframe: Literal['5m', '15m'] = '5m'
    mode: SignalMode = SignalMode.KEY_LEVEL
    backtest_days: int = Field(default=30, ge=1, le=3650)
    cash: float = Field(default=100, ge=10)
    opening_amount: float = Field(default=10, ge=0.1)
    margin_mode: MarginMode = MarginMode.ISOLATED
    leverage: float = Field(default=5, ge=1, le=150)
```

Keep cost fields. Remove `strategy`, `context_timeframe`, `context_lookback`, `entry_lookback`, `lookback`, `position_amount`, `take_profit_amount`, and `stop_loss_amount` from the active request. Extend `TradeItem` with mode, strategy source, margin mode, signal time/price, fill time/price, ATR snapshot, stop/target prices, expected stop/target amounts, `1h` environment, and `4h` filter label.

- [ ] **Step 4: Add a signal-mode engine entry point**

`BacktestEngine.run_signal_mode()` loads `{symbol}_{timeframe}.csv`, `{symbol}_1h.csv`, and `{symbol}_4h.csv`, filters the requested window without discarding indicator warm-up, builds snapshots, invokes `SignalSimulator`, and maps its output to `BacktestResult`. Keep the legacy `run()` method temporarily for old internal tests, but remove all route and optimizer calls to it.

- [ ] **Step 5: Replace strategy registries with mode options**

```python
MODE_OPTIONS = [
    {'value': 'KEY_LEVEL', 'label': '关键位', 'description': '支撑假跌破做多，阻力假突破做空'},
    {'value': 'RSI_REVERSAL', 'label': 'RSI 反转', 'description': 'RSI 极值配合布林带收回'},
    {'value': 'KEY_LEVEL_RSI', 'label': '关键位 + RSI 反转', 'description': '关键位优先，RSI 仅作兜底'},
]
```

Validate `opening_amount <= cash`; return a clear missing-data error listing `timeframe`, `1h`, and `4h` files. Do not fall back to a legacy strategy.

- [ ] **Step 6: Run focused API and engine tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_engine.py tests/test_routes.py tests/test_search_jobs.py -q`

Expected: PASS.

- [ ] **Step 7: Commit engine and API integration**

```powershell
git add src/backtest/engine.py src/web/schemas.py src/web/routes.py tests/test_engine.py tests/test_routes.py tests/test_search_jobs.py
git commit -m "Integrate signal modes with backtest API"
```

---

### Task 7: Simplify deterministic optimization

**Files:**
- Modify: `src/backtest/optimizer.py`
- Modify: `src/web/routes.py`
- Modify: `src/web/schemas.py`
- Modify: `tests/test_optimizer.py`
- Modify: `tests/test_search_jobs.py`

- [ ] **Step 1: Write failing candidate-shape tests**

```python
from dataclasses import asdict

from src.backtest.optimizer import build_stage_one_candidates


def test_candidates_only_search_approved_modes_timeframes_and_leverage() -> None:
    candidates = build_stage_one_candidates(
        modes=['KEY_LEVEL', 'RSI_REVERSAL', 'KEY_LEVEL_RSI'],
        available_entry_timeframes=['5m', '15m'], current_leverage=5,
        seed_key='ETH/USDT|ISOLATED',
    )
    assert {item.mode for item in candidates} == {'KEY_LEVEL', 'RSI_REVERSAL', 'KEY_LEVEL_RSI'}
    assert {item.timeframe for item in candidates} <= {'5m', '15m'}
    assert 'take_profit_amount' not in asdict(candidates[0])
    assert 'stop_loss_amount' not in asdict(candidates[0])
    assert 'opening_amount' not in asdict(candidates[0])
```

- [ ] **Step 2: Run optimizer tests and confirm the legacy candidate shape fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_optimizer.py tests/test_search_jobs.py -q`

Expected: FAIL on removed risk dimensions and old context/entry pairs.

- [ ] **Step 3: Replace `SearchCandidate` and candidate generation**

```python
@dataclass(frozen=True, slots=True)
class SearchCandidate:
    mode: str
    timeframe: str
    leverage: float
    margin_mode: str
```

Only include a timeframe when its entry CSV and the required `1h` and `4h` CSVs exist. Stage one stratifies modes, entry timeframes, margin mode, and the current leverage. Stage two explores neighboring leverage values only. Preserve deterministic SHA-256 seeds, time budgets, sample-out validation, random-window validation, and long-window validation.

- [ ] **Step 4: Remove exit-amount fields from optimizer responses and frontend application data**

`OptimizationCandidate` keeps mode, mode label, timeframe, margin mode, leverage, robustness fields, quality fields, and performance metrics. Remove strategy lookbacks, context timeframe/lookback, entry lookback, take-profit amount, and stop-loss amount.

- [ ] **Step 5: Run optimizer and job tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_optimizer.py tests/test_search_jobs.py -q`

Expected: PASS with deterministic candidates and no legacy risk dimensions.

- [ ] **Step 6: Commit optimizer simplification**

```powershell
git add src/backtest/optimizer.py src/web/routes.py src/web/schemas.py tests/test_optimizer.py tests/test_search_jobs.py
git commit -m "Restrict optimization to approved signal modes"
```

---

### Task 8: Rebuild the frontend contract

**Files:**
- Modify: `templates/backtest.html`
- Modify: `static/js/backtest.js`
- Modify: `static/css/style.css`
- Modify: `tests/test_styles.py`

- [ ] **Step 1: Write failing static contract tests**

```python
def test_signal_mode_and_margin_controls_replace_legacy_fields() -> None:
    html = TEMPLATE_PATH.read_text(encoding='utf-8')
    script = SCRIPT_PATH.read_text(encoding='utf-8')
    assert 'id="mode"' in html
    assert 'id="margin-mode"' in html
    assert 'id="opening-amount"' in html
    assert '账户总金额 (USDT)' in html
    assert html.index('id="cash"') < html.index('id="margin-mode"') < html.index('id="opening-amount"')
    assert 'take-profit-amount' not in html + script
    assert 'stop-loss-amount' not in html + script
    assert "mode: document.getElementById('mode').value" in script
    assert "margin_mode: document.getElementById('margin-mode').value" in script
```

- [ ] **Step 2: Run static tests and confirm failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_styles.py -q`

Expected: FAIL because the legacy strategy and risk controls still exist.

- [ ] **Step 3: Replace the controls and preserve the approved row layout**

The second row retains leverage. The third row is a dedicated three-column grid ordered exactly as account total, margin mode, and opening amount; responsive breakpoints collapse it to two and then one column.

```html
<div class="form-grid funds-grid">
  <div class="form-group"><label for="cash">账户总金额 (USDT)</label><input id="cash" type="number"></div>
  <div class="form-group"><label for="margin-mode">保证金模式</label><select id="margin-mode"><option value="ISOLATED" selected>逐仓</option><option value="CROSS">全仓</option></select></div>
  <div class="form-group"><label for="opening-amount">开仓金额 (USDT)</label><input id="opening-amount" type="number"></div>
</div>
```

- [ ] **Step 4: Replace payload validation and optimizer apply logic**

Allow only `5m/15m`; require opening amount not to exceed account total; submit `mode`, `margin_mode`, and `opening_amount`; remove context/lookback and manual exit amounts. Applying an optimization candidate writes mode, timeframe, margin mode, and leverage only.

- [ ] **Step 5: Add enriched trade columns**

Render source strategy, mode, margin mode, `1h` environment, `4h` label, signal/fill prices and times, frozen ATR, fixed stop/target prices, expected USDT outcomes, actual PnL, and fees. Keep the 50-row display limit.

- [ ] **Step 6: Run frontend and route tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_styles.py tests/test_routes.py -q`

Expected: PASS.

- [ ] **Step 7: Commit frontend changes**

```powershell
git add templates/backtest.html static/js/backtest.js static/css/style.css tests/test_styles.py
git commit -m "Update controls for signal and margin modes"
```

---

### Task 9: Remove legacy entry behavior from active coverage and verify end to end

**Files:**
- Modify: `tests/test_strategies.py`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Create: `scripts/validate_strategies.py`
- Create: `tests/test_validation_script.py`
- Create: `docs/strategy-validation.md`

- [ ] **Step 1: Replace active legacy-strategy tests**

Keep tests for generic fractional sizing or liquidation helpers only if still called. Replace assertions that register `SRBreakout`, `MovingAverageCross`, `RSIReversion`, or `KeyLevelScoring` as entry strategies with assertions that only the three stable mode identifiers appear in the index, API, and optimizer. Do not delete the legacy source files.

- [ ] **Step 2: Run the complete automated suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass with zero failures.

- [ ] **Step 3: Start the service and smoke-test the API**

Run:

```powershell
.\.venv\Scripts\python.exe main.py
```

In a second terminal, POST one request for each mode and both margin modes using `ETH/USDT`, `5m`, account total `100`, opening amount `10`, and leverage `5`. Expected: six successful responses, no duplicate trades per candle, and every trade contains frozen ATR and expected USDT outcome fields.

- [ ] **Step 4: Add the reproducible validation runner**

Write `tests/test_validation_script.py` first to prove that a mode passes only when average window return is positive, worst window is above `-40`, annual return is positive, drawdown is below `30`, profit factor is at least `1.05`, and annual trades are at least `50`. Implement `scripts/validate_strategies.py` with `evaluate_thresholds(metrics) -> tuple[bool, list[str]]`; loop over the three modes and two margin modes; call `BacktestEngine.run_signal_mode()` for 12 non-overlapping 30-day windows and one 365-day window; write the complete Markdown table to the requested output path.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_script.py -q`

Expected: PASS.

- [ ] **Step 5: Fetch the required closed 4-hour context data**

Run:

```powershell
.\.venv\Scripts\python.exe -m src.data.fetcher --symbol ETH/USDT --timeframe 4h --days 365
```

Expected: `data/ETH_USDT_4h.csv` exists and contains at least the requested validation period. The ignored market-data file is not staged.

- [ ] **Step 6: Run the approved historical validation matrix**

For `KEY_LEVEL`, `RSI_REVERSAL`, and `KEY_LEVEL_RSI`, run 12 non-overlapping 30-day windows plus the full-year window with taker fees, slippage, and funding enabled. Run isolated and cross modes separately. Write exact returns, worst window, annual return, maximum drawdown, profit factor, and trade count to `docs/strategy-validation.md`. Mark each mode `通过` only when every approved threshold is met; otherwise mark it `未通过验证` and do not enable it for future testnet execution.

Run:

```powershell
.\.venv\Scripts\python.exe scripts\validate_strategies.py --symbol ETH/USDT --days 365 --output docs\strategy-validation.md
```

Expected: six result rows, each with an explicit `通过` or `未通过验证` label and failure reasons.

- [ ] **Step 7: Synchronize project documentation**

Update `README.md` current features and request fields. Update the `CLAUDE.md` and `AGENTS.md` directory map, active modes, validation commands, and the rule that failed modes remain unavailable to automated testnet execution. Do not add historical narrative to the rule files.

- [ ] **Step 8: Run final verification**

Run:

```powershell
git diff --check
.\.venv\Scripts\python.exe -m pytest -q
git status --short
```

Expected: clean diff check, all tests pass, and status lists only the intended documentation and test changes for this task.

- [ ] **Step 9: Commit verification and documentation**

```powershell
git add tests/test_strategies.py tests/test_validation_script.py scripts/validate_strategies.py README.md CLAUDE.md AGENTS.md docs/strategy-validation.md
git commit -m "Document validated signal strategy modes"
```

Do not run `git push` without the user's explicit permission for that push.
