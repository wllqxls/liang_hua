# Yearly Multi-Timeframe Data Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a year-based data management module that fetches `5m`, `15m`, `1h`, and `4h` together and makes backtests/optimizer read from the selected yearly data directory.

**Architecture:** Add a focused data service in `src/data/yearly.py` for pathing, year-range fetch, merge/dedup/write, and status inspection. Keep web routes thin by validating requests and calling the service. Pass `data_year` through API, frontend, backtest, optimizer, and validation-adjacent helpers.

**Tech Stack:** Python 3.11+, pandas, ccxt/DataFetcher, FastAPI/Pydantic, Jinja2, vanilla JavaScript, pytest, Node syntax/harness checks.

---

## File structure

- Create `src/data/yearly.py`
  - Owns yearly data directory paths, active timeframes, fetch orchestration, CSV merge/dedup/write, and status inspection.
- Modify `src/data/fetcher.py`
  - Add optional `until` support to `fetch_ohlcv()` and `fetch_and_save()` so year fetches stop at year end.
- Modify `src/web/schemas.py`
  - Replace active data fetch schema with `symbol` + `year`.
  - Add `data_year` to backtest request.
  - Add yearly data status/fetch response fields.
- Modify `src/web/routes.py`
  - Update `/api/data-status` and `/api/fetch-data`.
  - Route backtest/optimizer engine data directories through `data/{year}`.
- Modify `templates/backtest.html`
  - Replace data fetch days UI with year selector and one yearly fetch button.
- Modify `static/js/backtest.js`
  - Send `year` for data fetch and `data_year` for backtest/optimizer.
  - Render data status for selected year.
- Modify tests:
  - `tests/test_fetcher.py`
  - `tests/test_routes.py`
  - `tests/test_optimizer.py`
  - `tests/frontend_harness.js`
  - `tests/test_styles.py` if selectors change.
- Modify docs:
  - `README.md`
  - `CLAUDE.md`
  - `AGENTS.md`

---

### Task 1: Yearly data service

**Files:**
- Create: `src/data/yearly.py`
- Test: `tests/test_yearly_data.py`

- [ ] **Step 1: Write failing tests for path, merge, status, and fetch loop**

Create `tests/test_yearly_data.py` with tests that assert:

```python
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.data.yearly import (
    YEARLY_TIMEFRAMES,
    fetch_symbol_year,
    inspect_year_data,
    merge_yearly_ohlcv,
    yearly_data_dir,
    yearly_data_path,
)


def frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    index = pd.to_datetime([item[0] for item in rows], utc=True)
    return pd.DataFrame(
        {
            'Open': [item[1] for item in rows],
            'High': [item[1] + 1 for item in rows],
            'Low': [item[1] - 1 for item in rows],
            'Close': [item[1] + 0.5 for item in rows],
            'Volume': [100 for _ in rows],
        },
        index=index,
    )


def test_yearly_paths_use_year_directory(tmp_path: Path) -> None:
    assert yearly_data_dir(tmp_path, 2025) == tmp_path / '2025'
    assert yearly_data_path(tmp_path, 'ETH/USDT', '5m', 2025) == tmp_path / '2025' / 'ETH_USDT_5m.csv'


def test_merge_yearly_ohlcv_deduplicates_sorts_and_trims_to_year() -> None:
    existing = frame([
        ('2024-12-31T23:55:00Z', 1),
        ('2025-01-01T00:00:00Z', 2),
        ('2025-01-01T00:05:00Z', 3),
    ])
    fetched = frame([
        ('2025-01-01T00:05:00Z', 30),
        ('2025-01-01T00:10:00Z', 4),
        ('2026-01-01T00:00:00Z', 5),
    ])

    merged = merge_yearly_ohlcv(existing, fetched, 2025)

    assert list(merged.index.astype(str)) == [
        '2025-01-01 00:00:00+00:00',
        '2025-01-01 00:05:00+00:00',
        '2025-01-01 00:10:00+00:00',
    ]
    assert merged.loc[pd.Timestamp('2025-01-01T00:05:00Z'), 'Open'] == 30


def test_inspect_year_data_counts_real_deduplicated_rows(tmp_path: Path) -> None:
    path = yearly_data_path(tmp_path, 'ETH/USDT', '5m', 2025)
    path.parent.mkdir(parents=True)
    frame([
        ('2025-01-01T00:05:00Z', 3),
        ('2025-01-01T00:00:00Z', 2),
        ('2025-01-01T00:05:00Z', 30),
    ]).to_csv(path)

    status = inspect_year_data(tmp_path, 'ETH/USDT', 2025)

    row = next(item for item in status if item.timeframe == '5m')
    assert row.exists is True
    assert row.rows == 2
    assert row.year == 2025


def test_fetch_symbol_year_fetches_all_required_timeframes_and_writes_files(tmp_path: Path) -> None:
    calls: list[tuple[str, str, datetime, datetime]] = []

    class FakeFetcher:
        def fetch_ohlcv(self, *, symbol: str, timeframe: str, since: datetime, until: datetime | None = None) -> pd.DataFrame:
            assert until is not None
            calls.append((symbol, timeframe, since, until))
            return frame([('2025-01-01T00:00:00Z', len(calls))])

    result = fetch_symbol_year('ETH/USDT', 2025, data_dir=tmp_path, fetcher=FakeFetcher())

    assert [call[1] for call in calls] == list(YEARLY_TIMEFRAMES)
    assert all(call[0] == 'ETH/USDT' for call in calls)
    assert calls[0][2].isoformat() == '2025-01-01T00:00:00+00:00'
    assert calls[0][3].isoformat() == '2025-12-31T23:59:59+00:00'
    assert {item.timeframe for item in result} == set(YEARLY_TIMEFRAMES)
    assert yearly_data_path(tmp_path, 'ETH/USDT', '4h', 2025).exists()
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_yearly_data.py -q
```

Expected: fail because `src.data.yearly` does not exist.

- [ ] **Step 3: Implement `src/data/yearly.py`**

Implement:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd

from src.data.fetcher import DataFetcher

YEARLY_TIMEFRAMES: tuple[str, ...] = ('5m', '15m', '1h', '4h')
OHLCV_COLUMNS: tuple[str, ...] = ('Open', 'High', 'Low', 'Close', 'Volume')


class OhlcvFetcher(Protocol):
    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: datetime | None = None,
    ) -> pd.DataFrame:
        ...


@dataclass(frozen=True)
class YearlyDataStatus:
    symbol: str
    timeframe: str
    year: int
    exists: bool
    rows: int | None = None
    file_size_kb: float | None = None


def validate_year(year: int) -> int:
    if year < 2017 or year > datetime.now(timezone.utc).year + 1:
        raise ValueError('年份超出支持范围')
    return year


def yearly_data_dir(data_dir: str | Path, year: int) -> Path:
    validate_year(year)
    return Path(data_dir) / str(year)


def yearly_data_path(data_dir: str | Path, symbol: str, timeframe: str, year: int) -> Path:
    if timeframe not in YEARLY_TIMEFRAMES:
        raise ValueError(f'暂不支持的 K 线周期: {timeframe}')
    safe_symbol = symbol.replace('/', '_')
    return yearly_data_dir(data_dir, year) / f'{safe_symbol}_{timeframe}.csv'


def year_bounds(year: int) -> tuple[datetime, datetime]:
    validate_year(year)
    return (
        datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
    )


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    normalized = df.copy()
    normalized.index = pd.to_datetime(normalized.index, utc=True)
    normalized = normalized.sort_index()
    return normalized[list(OHLCV_COLUMNS)]


def merge_yearly_ohlcv(existing: pd.DataFrame | None, fetched: pd.DataFrame, year: int) -> pd.DataFrame:
    frames = []
    if existing is not None and not existing.empty:
        frames.append(_normalize_ohlcv(existing))
    if not fetched.empty:
        frames.append(_normalize_ohlcv(fetched))
    if not frames:
        return pd.DataFrame(columns=list(OHLCV_COLUMNS))
    merged = pd.concat(frames).sort_index()
    merged = merged[~merged.index.duplicated(keep='last')]
    start, end = year_bounds(year)
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    merged = merged[(merged.index >= start_ts) & (merged.index <= end_ts)]
    return merged[list(OHLCV_COLUMNS)]


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)


def inspect_year_data(data_dir: str | Path, symbol: str, year: int) -> list[YearlyDataStatus]:
    statuses: list[YearlyDataStatus] = []
    for timeframe in YEARLY_TIMEFRAMES:
        path = yearly_data_path(data_dir, symbol, timeframe, year)
        exists = path.exists()
        rows: int | None = None
        file_size_kb: float | None = None
        if exists:
            df = _read_csv(path)
            normalized = merge_yearly_ohlcv(None, df if df is not None else pd.DataFrame(), year)
            rows = len(normalized)
            file_size_kb = round(path.stat().st_size / 1024, 1)
        statuses.append(YearlyDataStatus(symbol=symbol, timeframe=timeframe, year=year, exists=exists, rows=rows, file_size_kb=file_size_kb))
    return statuses


def fetch_symbol_year(
    symbol: str,
    year: int,
    *,
    data_dir: str | Path = './data',
    fetcher: OhlcvFetcher | None = None,
) -> list[YearlyDataStatus]:
    validate_year(year)
    fetcher = fetcher or DataFetcher()
    since, until = year_bounds(year)
    for timeframe in YEARLY_TIMEFRAMES:
        path = yearly_data_path(data_dir, symbol, timeframe, year)
        existing = _read_csv(path)
        fetched = fetcher.fetch_ohlcv(symbol=symbol, timeframe=timeframe, since=since, until=until)
        merged = merge_yearly_ohlcv(existing, fetched, year)
        _write_csv(path, merged)
    return inspect_year_data(data_dir, symbol, year)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_yearly_data.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/data/yearly.py tests/test_yearly_data.py
git commit -m "Add yearly multi-timeframe data service"
```

---

### Task 2: Fetcher bounded range support

**Files:**
- Modify: `src/data/fetcher.py`
- Test: `tests/test_fetcher.py`

- [ ] **Step 1: Add failing tests for `until` support**

Add a test using a fake exchange that returns candles beyond the `until` timestamp and assert `fetch_ohlcv(..., until=...)` filters them out and stops requesting after the range is complete.

- [ ] **Step 2: Run focused fetcher tests and verify RED**

Run:

```powershell
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_fetcher.py -q
```

Expected: fail because `until` is unsupported.

- [ ] **Step 3: Implement `until` in `fetch_ohlcv()` and `fetch_and_save()`**

Add `until: datetime | None = None`; convert it to milliseconds; after each batch filter rows where timestamp `<= until_ms`; stop once exchange returns a candle at or beyond `until_ms`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_fetcher.py tests/test_yearly_data.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/data/fetcher.py tests/test_fetcher.py
git commit -m "Support bounded OHLCV fetch ranges"
```

---

### Task 3: API schemas and routes

**Files:**
- Modify: `src/web/schemas.py`
- Modify: `src/web/routes.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Add failing route tests**

Add tests that assert:

- `GET /api/data-status?symbol=ETH/USDT&year=2025` returns four rows for the selected year.
- `POST /api/fetch-data` with `{"symbol": "ETH/USDT", "year": 2025}` calls one backend function and returns four items.
- Unsupported symbols and invalid years return user-readable errors.

- [ ] **Step 2: Run route tests and verify RED**

Run:

```powershell
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_routes.py -q
```

Expected: fail because schemas/routes still expect `timeframe` and `days`.

- [ ] **Step 3: Update schemas**

Change active data schemas to:

```python
class DataFetchRequest(BaseModel):
    symbol: str = Field(default='BTC/USDT', description='交易对象')
    year: int = Field(default_factory=lambda: datetime.now(timezone.utc).year, ge=2017, le=2100, description='数据年份')


class DataStatus(BaseModel):
    symbol: str
    timeframe: str
    year: int
    exists: bool
    rows: int | None = None
    file_size_kb: float | None = None


class DataFetchResponse(BaseModel):
    success: bool
    symbol: str
    year: int
    items: list[DataStatus] = Field(default_factory=list)
    error: str | None = None
```

Add to `BacktestRequest`:

```python
data_year: int = Field(default_factory=lambda: datetime.now(timezone.utc).year, ge=2017, le=2100, description='本地数据年份')
```

- [ ] **Step 4: Update routes**

Use `inspect_year_data()` and `fetch_symbol_year()` for `/api/data-status` and `/api/fetch-data`.

- [ ] **Step 5: Run route tests**

Run:

```powershell
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_routes.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add src/web/schemas.py src/web/routes.py tests/test_routes.py
git commit -m "Add yearly data API"
```

---

### Task 4: Backtest and optimizer year-aware data directories

**Files:**
- Modify: `src/web/routes.py`
- Modify: `src/backtest/optimizer.py` if helper signatures require it
- Test: `tests/test_routes.py`
- Test: `tests/test_optimizer.py`

- [ ] **Step 1: Add failing tests**

Assert `BacktestEngine` is created with `Path('./data') / str(req.data_year)` for backtest and optimizer paths. Assert helper functions that inspect CSV bounds use the same yearly directory.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_routes.py tests/test_optimizer.py -q
```

Expected: fail because routes still use `./data`.

- [ ] **Step 3: Implement year-aware paths**

Add a helper:

```python
def _request_data_dir(year: int) -> Path:
    return Path('./data') / str(year)
```

Use it in backtest, optimizer job creation, progressive optimizer, and `_load_data_bounds()`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_routes.py tests/test_optimizer.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/web/routes.py src/backtest/optimizer.py tests/test_routes.py tests/test_optimizer.py
git commit -m "Use yearly data directories for backtests"
```

---

### Task 5: Frontend yearly data controls

**Files:**
- Modify: `templates/backtest.html`
- Modify: `static/js/backtest.js`
- Modify: `static/css/style.css` if layout needs it
- Test: `tests/frontend_harness.js`
- Test: `tests/test_styles.py`

- [ ] **Step 1: Add failing frontend harness assertions**

Assert:

- `fetch-data-btn` text is `拉取指定年份全部周期`.
- `fetch-days` no longer exists.
- `data-year` defaults to the current year.
- fetch payload is `{symbol, year}` only.
- backtest/optimizer payload includes `data_year`.

- [ ] **Step 2: Run frontend tests and verify RED**

Run:

```powershell
node tests/frontend_harness.js
```

Expected: fail because current UI sends `days/timeframe`.

- [ ] **Step 3: Update HTML**

Replace the old days input with:

```html
<div class="form-group compact">
    <label for="data-year">数据年份</label>
    <input type="number" id="data-year" min="2017" max="2100">
</div>
<button id="fetch-data-btn" class="btn-secondary" onclick="fetchSelectedData()">拉取指定年份全部周期</button>
```

Remove old data fetch days wording.

- [ ] **Step 4: Update JS**

Use `data-year` in:

- `loadDataStatus()`
- `fetchSelectedData()`
- `buildBacktestPayload()`
- optimizer payload creation

Remove looped frontend timeframe fetches. The backend now loops all four periods.

- [ ] **Step 5: Run frontend and style tests**

Run:

```powershell
node --check static/js/backtest.js
node tests/frontend_harness.js
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest tests/test_styles.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add templates/backtest.html static/js/backtest.js static/css/style.css tests/frontend_harness.js tests/test_styles.py
git commit -m "Update frontend yearly data controls"
```

---

### Task 6: Documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update docs**

Document:

- `data/{year}/{SYMBOL}_{TIMEFRAME}.csv`
- active fetch periods are `5m`, `15m`, `1h`, `4h`
- one-click yearly data fetch
- backtest/optimizer use selected `data_year`
- root-level `data/*.csv` is compatibility only, not the new active UI target.

- [ ] **Step 2: Run complete verification**

Run:

```powershell
git diff --check
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest -q
node --check static/js/backtest.js
node tests/frontend_harness.js
git status --short
```

Expected: all pass; status only lists intended files before commit.

- [ ] **Step 3: Commit**

```powershell
git add README.md CLAUDE.md AGENTS.md
git commit -m "Document yearly data workflow"
```

- [ ] **Step 4: Final status**

Run:

```powershell
git log --oneline -6
git status --short
```

Expected: branch has task commits and clean working tree.
