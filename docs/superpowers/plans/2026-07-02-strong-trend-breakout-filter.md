# Strong Trend Breakout Filter V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require trend strength, continuing trend momentum, and correct price position before `SRBreakout` may enter.

**Architecture:** Extend the existing look-ahead-safe context merge with fast-MA and normalized three-period momentum fields, then apply all three checks in the dedicated breakout gate. Keep other strategies unchanged and validate both rolling risk and full-year quality.

**Tech Stack:** Python, pandas, backtesting.py, pytest

---

### Task 1: Add look-ahead-safe momentum and fast-MA fields

**Files:**
- Modify: `src/backtest/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write failing tests**

Add assertions for the new fields and compare results with and without an extreme unclosed final candle:

```python
assert 'ContextFastMA' in merged.columns
assert 'ContextTrendMomentum' in merged.columns
assert with_future.loc[entry_time, 'ContextFastMA'] == baseline.loc[entry_time, 'ContextFastMA']
assert with_future.loc[entry_time, 'ContextTrendMomentum'] == baseline.loc[
    entry_time, 'ContextTrendMomentum'
]
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_engine.py -q`

Expected: FAIL because both fields are absent.

- [ ] **Step 3: Implement the fields before the existing shift**

```python
context_features['ContextFastMA'] = fast_ma
context_features['ContextTrendMomentum'] = (
    (fast_ma - fast_ma.shift(3)) / context_features['ContextATR']
)
```

The existing `context_features.shift(1)` must remain after all fields.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_engine.py -q`

Expected: all engine tests pass.

### Task 2: Enforce all three confirmations

**Files:**
- Modify: `src/strategies/risk.py`
- Test: `tests/test_strategies.py`

- [ ] **Step 1: Extend failing gate tests**

Extend `FakeContextData` with momentum, close, and fast MA. Verify aligned values pass and each contradictory value fails:

```python
data = FakeContextData(trend=1, strength=1.2, momentum=0.2, close=110, fast_ma=100)
assert strong_context_trend_allows_side(data, 'long') is True
assert strong_context_trend_allows_side(
    FakeContextData(1, 1.2, -0.1, 110, 100), 'long'
) is False
assert strong_context_trend_allows_side(
    FakeContextData(1, 1.2, 0.2, 90, 100), 'long'
) is False
```

Add symmetric short assertions and missing-field rejection.

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_strategies.py -q`

Expected: FAIL because the first-version helper ignores momentum and price position.

- [ ] **Step 3: Implement the three-part gate**

Read `ContextTrendMomentum`, `ContextClose`, and `ContextFastMA`. Reject missing values. For long require positive trend, positive momentum, and close above fast MA; for short require all inverse conditions.

```python
if any(value is None for value in [trend, strength, momentum, close, fast_ma]):
    return False
if strength < minimum_strength:
    return False
if side == 'long':
    return trend > 0 and momentum > 0 and close > fast_ma
if side == 'short':
    return trend < 0 and momentum < 0 and close < fast_ma
return False
```

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_strategies.py tests\test_engine.py -q`

Expected: all focused tests pass.

### Task 3: Preserve exit distances across leverage changes

**Files:**
- Modify: `src/backtest/optimizer.py`
- Test: `tests/test_optimizer.py`

- [ ] **Step 1: Write a failing leverage-scaling test**

Use a base candidate at `x10`, take profit `1.5`, and stop loss `0.5`. Assert that the generated `x3` pool contains the unchanged-risk-profile candidate with take profit `0.45` and stop loss `0.15`.

```python
x3 = [item for item in candidates if item.leverage == 3]
assert any(item.take_profit_amount == 0.45 and item.stop_loss_amount == 0.15 for item in x3)
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_optimizer.py -q`

Expected: FAIL because amounts currently remain based on the x10 candidate.

- [ ] **Step 3: Scale amounts before local risk factors**

For each generated leverage use `leverage_ratio = leverage / base.leverage`, then multiply both base amounts by this ratio before applying `tp_factor` and `sl_factor`.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_optimizer.py -q`

Expected: all optimizer tests pass.

### Task 4: Verify code and strategy performance

**Files:**
- No additional production changes

- [ ] **Step 1: Run all tests**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Run twelve non-overlapping 30-day windows**

Use ETH/USDT, `1h + 5m`, context lookback `192`, entry lookback `30`, cash `10`, position `2`, leverage `10`, take profit `1.5`, stop loss `0.5`, and configured costs.

Acceptance with `x3`, take profit `0.45`, and stop loss `0.15`: mean return above `0%` and worst return above `-40%`.

- [ ] **Step 3: Run the full-year aggregate**

Use the same fixed parameters over the entire common 1h/5m date range. Calculate quality with the existing trade list.

Acceptance: positive total return, drawdown better than `-30%`, profit factor at least `1.05`, and at least 50 trades.

- [ ] **Step 4: Inspect and commit only if all gates pass**

Run `git diff --check`, confirm only planned files changed, then commit with `Filter breakouts by persistent context trend`. If any performance gate fails, do not tune thresholds and do not commit the strategy implementation.
