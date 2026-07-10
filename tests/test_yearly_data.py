from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.data.yearly import (
    YEARLY_TIMEFRAMES,
    fetch_symbol_year,
    inspect_year_data,
    merge_yearly_ohlcv,
    validate_year,
    year_bounds,
    yearly_data_dir,
    yearly_data_path,
)


def _frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
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


def test_year_bounds_cover_selected_utc_year() -> None:
    start, end = year_bounds(2025)

    assert start.isoformat() == '2025-01-01T00:00:00+00:00'
    assert end.isoformat() == '2025-12-31T23:59:59+00:00'


def test_validate_year_rejects_unsupported_years() -> None:
    with pytest.raises(ValueError, match='年份超出支持范围'):
        validate_year(2016)


def test_merge_yearly_ohlcv_deduplicates_sorts_and_trims_to_year() -> None:
    existing = _frame(
        [
            ('2024-12-31T23:55:00Z', 1),
            ('2025-01-01T00:00:00Z', 2),
            ('2025-01-01T00:05:00Z', 3),
        ]
    )
    fetched = _frame(
        [
            ('2025-01-01T00:05:00Z', 30),
            ('2025-01-01T00:10:00Z', 4),
            ('2026-01-01T00:00:00Z', 5),
        ]
    )

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
    _frame(
        [
            ('2025-01-01T00:05:00Z', 3),
            ('2025-01-01T00:00:00Z', 2),
            ('2025-01-01T00:05:00Z', 30),
        ]
    ).to_csv(path)

    status = inspect_year_data(tmp_path, 'ETH/USDT', 2025)

    row = next(item for item in status if item.timeframe == '5m')
    missing_row = next(item for item in status if item.timeframe == '15m')
    assert row.exists is True
    assert row.rows == 2
    assert row.year == 2025
    assert row.file_size_kb is not None
    assert missing_row.exists is False
    assert missing_row.rows is None


def test_fetch_symbol_year_fetches_all_required_timeframes_and_writes_files(tmp_path: Path) -> None:
    calls: list[tuple[str, str, datetime, datetime]] = []

    class FakeFetcher:
        def fetch_ohlcv(
            self,
            *,
            symbol: str,
            timeframe: str,
            since: datetime,
            until: datetime | None = None,
        ) -> pd.DataFrame:
            assert until is not None
            calls.append((symbol, timeframe, since, until))
            return _frame([('2025-01-01T00:00:00Z', len(calls))])

    result = fetch_symbol_year('ETH/USDT', 2025, data_dir=tmp_path, fetcher=FakeFetcher())

    assert [call[1] for call in calls] == list(YEARLY_TIMEFRAMES)
    assert all(call[0] == 'ETH/USDT' for call in calls)
    assert calls[0][2].isoformat() == '2025-01-01T00:00:00+00:00'
    assert calls[0][3].isoformat() == '2025-12-31T23:59:59+00:00'
    assert {item.timeframe for item in result} == set(YEARLY_TIMEFRAMES)
    assert yearly_data_path(tmp_path, 'ETH/USDT', '4h', 2025).exists()


def test_fetch_symbol_year_merges_with_existing_csv(tmp_path: Path) -> None:
    path = yearly_data_path(tmp_path, 'ETH/USDT', '5m', 2025)
    path.parent.mkdir(parents=True)
    _frame([('2025-01-01T00:00:00Z', 1)]).to_csv(path)

    class FakeFetcher:
        def fetch_ohlcv(self, **kwargs: Any) -> pd.DataFrame:
            timeframe = kwargs['timeframe']
            if timeframe == '5m':
                return _frame(
                    [
                        ('2025-01-01T00:00:00Z', 10),
                        ('2025-01-01T00:05:00Z', 2),
                    ]
                )
            return _frame([('2025-01-01T00:00:00Z', 1)])

    fetch_symbol_year('ETH/USDT', 2025, data_dir=tmp_path, fetcher=FakeFetcher())

    saved = pd.read_csv(path, index_col=0, parse_dates=True)
    assert len(saved) == 2
    assert saved.iloc[0]['Open'] == 10
