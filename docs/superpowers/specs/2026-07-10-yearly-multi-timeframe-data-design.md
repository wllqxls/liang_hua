# Yearly Multi-Timeframe Data Management Design

## Goal

Replace the current single-timeframe data fetch workflow with a year-based data management module that fetches all required backtest timeframes in one action.

The user-facing behavior is:

- choose a trading symbol;
- choose a year, defaulting to the current calendar year;
- click `拉取指定年份全部周期`;
- the system fetches `5m`, `15m`, `1h`, and `4h` for that symbol and year;
- the data status table shows whether each timeframe exists for that selected year and how many de-duplicated CSV rows it contains.

## Non-goals

- Do not implement real-time streaming data.
- Do not implement progress polling or background jobs in this pass.
- Do not keep the old single-timeframe fetch button as an active UI path.
- Do not write market CSV files into git.

## Data layout

New yearly data files live under:

```text
data/{year}/{SYMBOL}_{TIMEFRAME}.csv
```

Example:

```text
data/2025/ETH_USDT_5m.csv
data/2025/ETH_USDT_15m.csv
data/2025/ETH_USDT_1h.csv
data/2025/ETH_USDT_4h.csv
```

`SYMBOL` replaces `/` with `_`.

The active fetch timeframes are exactly:

```text
5m, 15m, 1h, 4h
```

Existing root-level files such as `data/ETH_USDT_5m.csv` may remain for compatibility, but the new data management UI, status API, backtest, optimizer, and validation paths must use the selected yearly directory.

## Fetch semantics

The backend exposes one unified year fetch operation:

```python
fetch_symbol_year(symbol: str, year: int) -> list[DataStatus]
```

It computes the UTC range:

```text
{year}-01-01 00:00:00 UTC
through
{year}-12-31 23:59:59 UTC
```

The implementation fetches all four timeframes in one backend call. Each timeframe is saved to `data/{year}`.

When an existing yearly CSV is present:

1. load the old CSV;
2. append the newly fetched rows;
3. sort by timestamp;
4. drop duplicate timestamps, keeping the newest fetched row;
5. trim rows to the requested year;
6. overwrite the CSV.

The row count reported to the UI is the real de-duplicated row count in the saved CSV.

## API contract

### Data status

```http
GET /api/data-status?symbol=ETH/USDT&year=2025
```

Returns four rows for the selected symbol and year.

Each row includes:

- `symbol`
- `timeframe`
- `year`
- `exists`
- `rows`
- `file_size_kb`

### Data fetch

```http
POST /api/fetch-data
```

Request:

```json
{
  "symbol": "ETH/USDT",
  "year": 2025
}
```

Response:

```json
{
  "success": true,
  "symbol": "ETH/USDT",
  "year": 2025,
  "items": [
    {"symbol": "ETH/USDT", "timeframe": "5m", "year": 2025, "exists": true, "rows": 105120, "file_size_kb": 12345.6},
    {"symbol": "ETH/USDT", "timeframe": "15m", "year": 2025, "exists": true, "rows": 35040, "file_size_kb": 4567.8},
    {"symbol": "ETH/USDT", "timeframe": "1h", "year": 2025, "exists": true, "rows": 8760, "file_size_kb": 1234.5},
    {"symbol": "ETH/USDT", "timeframe": "4h", "year": 2025, "exists": true, "rows": 2190, "file_size_kb": 456.7}
  ],
  "error": null
}
```

The old single-timeframe request fields `timeframe` and `days` are no longer part of the active frontend path.

## Backtest and optimizer integration

`BacktestRequest` gains:

```python
data_year: int
```

The default is the current UTC year so existing callers that omit it remain usable.

When running backtests or optimizer searches, the backend constructs:

```python
data_dir = Path('data') / str(req.data_year)
```

and passes that directory to `BacktestEngine`.

Optimizer helper functions that directly inspect file paths must also use the selected yearly directory.

## Frontend behavior

The data panel changes to:

- a symbol source from the current symbol select;
- a year input/select defaulting to the current year;
- one button: `拉取指定年份全部周期`;
- a refresh button;
- a Chinese status message.

The old `拉取天数` field and old per-timeframe fetch behavior are removed.

The DataGrid columns remain:

- `交易对象`
- `K线周期`
- `状态`
- `行数`

The status is always evaluated for the currently selected year.

Backtest and optimizer payloads include the selected `data_year`.

## Error handling

- Unsupported symbol returns a user-readable Chinese error.
- Invalid year returns a validation error.
- Exchange/network errors return a user-readable Chinese error and do not claim partial success as full success.
- If one timeframe fails during the year fetch, the response is unsuccessful and includes the error. Files already written by earlier timeframes remain on disk because market data writes are non-transactional CSV writes.

## Testing strategy

Automated tests must cover:

- year directory path generation;
- unified fetch loops exactly `5m`, `15m`, `1h`, `4h`;
- merge, sort, de-duplicate, trim, and overwrite behavior;
- status row counts from real CSV content after de-duplication;
- data status API filters by symbol and year;
- fetch API accepts `symbol` + `year` and rejects unsupported inputs;
- backtest and optimizer instantiate/read from `data/{year}`;
- frontend sends `year` instead of `days/timeframe` for data fetch;
- frontend includes `data_year` in backtest and optimizer payloads.

## Compatibility notes

Root-level `data/*.csv` files are not deleted. They are simply no longer the active data-management target.

Market data remains ignored by git.
