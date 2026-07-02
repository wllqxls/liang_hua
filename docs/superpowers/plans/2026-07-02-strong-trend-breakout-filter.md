# Strong Trend Breakout Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `SRBreakout` trade only when the last fully closed context candle shows a strong trend aligned with the breakout direction.

**Architecture:** `BacktestEngine` derives `ContextTrendStrength` from moving-average separation divided by ATR and shifts it before merging. A dedicated helper applies this strict gate only to `SRBreakout`; other strategies keep their existing behavior.

**Tech Stack:** Python, pandas, backtesting.py, pytest

---

### Task 1: Add look-ahead-safe trend strength

**Files:**
- Modify: `src/backtest/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write failing tests**

Assert that merged context includes non-negative `ContextTrendStrength`. Extend the unclosed-candle regression test by comparing strength with and without an extreme final context candle:

```python
assert 'ContextTrendStrength' in merged.columns
assert merged['ContextTrendStrength'].dropna().ge(0).all()
assert with_future.loc[entry_time, 'ContextTrendStrength'] == baseline.loc[
    entry_time, 'ContextTrendStrength'
]
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_engine.py -q`

Expected: FAIL because `ContextTrendStrength` is absent.

- [ ] **Step 3: Implement the feature**

After calculating ATR, add:

```python
context_features['ContextTrendStrength'] = (
    (fast_ma - slow_ma).abs() / context_features['ContextATR']
)
```

Keep the existing `context_features = context_features.shift(1)` after every context column.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_engine.py -q`

Expected: all engine tests pass.

### Task 2: Gate only breakout entries

**Files:**
- Modify: `src/strategies/risk.py`
- Modify: `src/strategies/sr_breakout.py`
- Test: `tests/test_strategies.py`

- [ ] **Step 1: Write failing helper tests**

Use small data stubs to verify strong aligned trends pass while wrong direction, strength below `1.0`, and missing strength fail:

```python
data = FakeContextData(trend=1, strength=1.2)
assert strong_context_trend_allows_side(data, 'long') is True
assert strong_context_trend_allows_side(data, 'short') is False
assert strong_context_trend_allows_side(FakeContextData(1, 0.99), 'long') is False
assert strong_context_trend_allows_side(FakeContextData(1, None), 'long') is False
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_strategies.py -q`

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Implement the helper and wire it to SRBreakout**

```python
def strong_context_trend_allows_side(
    data: object,
    side: str,
    minimum_strength: float = 1.0,
) -> bool:
    trend = _latest_data_value(data, 'ContextTrend')
    strength = _latest_data_value(data, 'ContextTrendStrength')
    if trend is None or strength is None or strength < minimum_strength:
        return False
    if side == 'long':
        return trend > 0
    if side == 'short':
        return trend < 0
    return False
```

Replace both `context_allows_side` calls in `SRBreakout`; leave other strategies unchanged.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_strategies.py tests\test_engine.py -q`

Expected: all focused tests pass.

### Task 3: Explain the behavior in the UI

**Files:**
- Modify: `src/web/routes.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Write a failing description test**

```python
option = next(item for item in STRATEGY_OPTIONS if item['value'] == 'SRBreakout')
assert '高周期强趋势' in option['description']
assert '震荡时不交易' in option['description']
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_routes.py::test_breakout_description_mentions_strong_context_filter -q`

Expected: FAIL against the old description.

- [ ] **Step 3: Update the description**

```python
'description': '规则策略：只在高周期强趋势中交易，向上突破做多、向下突破做空，震荡时不交易。'
```

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_routes.py -q`

Expected: all route tests pass.

### Task 4: Full verification and rolling benchmark

**Files:**
- No additional production changes

- [ ] **Step 1: Run all tests**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Run twelve fixed 30-day windows**

Use ETH/USDT, `1h + 5m`, context lookback `192`, entry lookback `30`, cash `10`, position `2`, leverage `10`, take profit `1.5`, stop loss `0.5`, and configured costs.

Acceptance: mean return above `0%`, worst return above `-40%`, and at least `8/12` windows pass strict quality filtering.

- [ ] **Step 3: Inspect and commit**

Run `git diff --check`, confirm only planned files changed, then commit with `Filter breakouts by strong context trend`. Do not push until the user explicitly authorizes it.
