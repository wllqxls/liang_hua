"""Year-based multi-timeframe local market data management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd

from src.data.fetcher import DataFetcher

YEARLY_TIMEFRAMES: tuple[str, ...] = ('5m', '15m', '1h', '4h')
OHLCV_COLUMNS: tuple[str, ...] = ('Open', 'High', 'Low', 'Close', 'Volume')
MIN_SUPPORTED_YEAR = 2017
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / 'data'


class OhlcvFetcher(Protocol):
    """Fetcher protocol used by the yearly data service."""

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: datetime | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV rows for one symbol/timeframe/range."""
        ...


@dataclass(frozen=True)
class YearlyDataStatus:
    """Status for one local yearly CSV file."""

    symbol: str
    timeframe: str
    year: int
    exists: bool
    rows: int | None = None
    file_size_kb: float | None = None


def validate_year(year: int) -> int:
    """Validate the user-selected data year."""
    max_year = datetime.now(timezone.utc).year + 1
    if year < MIN_SUPPORTED_YEAR or year > max_year:
        raise ValueError('年份超出支持范围')
    return year


def yearly_data_dir(data_dir: str | Path, year: int) -> Path:
    """Return the directory for one data year."""
    validate_year(year)
    return Path(data_dir) / str(year)


def yearly_data_path(data_dir: str | Path, symbol: str, timeframe: str, year: int) -> Path:
    """Return the CSV path for one yearly symbol/timeframe file."""
    if timeframe not in YEARLY_TIMEFRAMES:
        raise ValueError(f'暂不支持的 K 线周期: {timeframe}')
    safe_symbol = symbol.replace('/', '_')
    return yearly_data_dir(data_dir, year) / f'{safe_symbol}_{timeframe}.csv'


def year_bounds(year: int) -> tuple[datetime, datetime]:
    """Return inclusive UTC fetch bounds for one calendar year."""
    validate_year(year)
    return (
        datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
    )


def merge_yearly_ohlcv(existing: pd.DataFrame | None, fetched: pd.DataFrame, year: int) -> pd.DataFrame:
    """Merge old and fetched OHLCV rows, keeping only unique sorted rows inside year."""
    frames: list[pd.DataFrame] = []
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


def inspect_year_data(data_dir: str | Path, symbol: str, year: int) -> list[YearlyDataStatus]:
    """Inspect yearly CSV presence and de-duplicated row counts for all active timeframes."""
    statuses: list[YearlyDataStatus] = []
    for timeframe in YEARLY_TIMEFRAMES:
        path = yearly_data_path(data_dir, symbol, timeframe, year)
        if not path.exists():
            statuses.append(
                YearlyDataStatus(symbol=symbol, timeframe=timeframe, year=year, exists=False)
            )
            continue

        df = _read_csv(path)
        normalized = merge_yearly_ohlcv(None, df if df is not None else pd.DataFrame(), year)
        statuses.append(
            YearlyDataStatus(
                symbol=symbol,
                timeframe=timeframe,
                year=year,
                exists=True,
                rows=len(normalized),
                file_size_kb=round(path.stat().st_size / 1024, 1),
            )
        )
    return statuses


def fetch_symbol_year(
    symbol: str,
    year: int,
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    fetcher: OhlcvFetcher | None = None,
) -> list[YearlyDataStatus]:
    """Fetch all active timeframes for one symbol/year and return refreshed statuses."""
    validate_year(year)
    ohlcv_fetcher = fetcher or DataFetcher()
    since, until = year_bounds(year)

    for timeframe in YEARLY_TIMEFRAMES:
        path = yearly_data_path(data_dir, symbol, timeframe, year)
        existing = _read_csv(path)
        fetched = ohlcv_fetcher.fetch_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            until=until,
        )
        merged = merge_yearly_ohlcv(existing, fetched, year)
        _write_csv(path, merged)

    return inspect_year_data(data_dir, symbol, year)


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=list(OHLCV_COLUMNS))
    normalized = df.copy()
    normalized.index = pd.to_datetime(normalized.index, utc=True)
    normalized = normalized.sort_index()
    return normalized[list(OHLCV_COLUMNS)]


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
