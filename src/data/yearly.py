"""Year-based multi-timeframe local market data management."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from src.data.order_flow import (
    FuturesKlineArchiveSpec,
    download_public_kline_archive,
    read_archive_csv,
)

YEARLY_TIMEFRAMES: tuple[str, ...] = ('5m', '15m', '1h', '4h')
OHLCV_COLUMNS: tuple[str, ...] = ('Open', 'High', 'Low', 'Close', 'Volume')
MIN_SUPPORTED_YEAR = 2017
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / 'data'
MARKET_SOURCE = 'BINANCE_UM_FUTURES_ARCHIVE'
ARCHIVE_ROOT_NAME = 'order_flow/binance_um'
_FUTURES_KLINE_COLUMNS = (
    'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
    'quote_volume', 'count', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore',
)


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
    source: str | None = None


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


def yearly_source_path(data_dir: str | Path, symbol: str, year: int) -> Path:
    safe_symbol = symbol.replace('/', '_')
    return yearly_data_dir(data_dir, year) / f'{safe_symbol}_market_source.json'


def yearly_data_source(data_dir: str | Path, symbol: str, year: int) -> str | None:
    path = yearly_source_path(data_dir, symbol, year)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get('symbol') != symbol or payload.get('year') != year:
        return None
    source = payload.get('source')
    return str(source) if source else None


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
    source = yearly_data_source(data_dir, symbol, year)
    for timeframe in YEARLY_TIMEFRAMES:
        path = yearly_data_path(data_dir, symbol, timeframe, year)
        if not path.exists():
            statuses.append(
                YearlyDataStatus(
                    symbol=symbol, timeframe=timeframe, year=year, exists=False, source=source,
                )
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
                source=source,
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
    if fetcher is None:
        return fetch_binance_um_futures_year(symbol, year, data_dir=data_dir)
    ohlcv_fetcher = fetcher
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


def fetch_binance_um_futures_year(
    symbol: str,
    year: int,
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> list[YearlyDataStatus]:
    """Build one completed USD-M futures year from verified monthly 5m archives."""
    validate_year(year)
    current_year = datetime.now(timezone.utc).year
    if year >= current_year:
        raise ValueError('基础行情年度归档只支持已经结束的完整年份')
    archive_symbol = symbol.replace('/', '')
    archive_root = Path(data_dir) / ARCHIVE_ROOT_NAME
    monthly_frames: list[pd.DataFrame] = []
    available_months: list[int] = []
    for month in range(1, 13):
        period = f'{year}-{month:02d}'
        spec = FuturesKlineArchiveSpec(
            archive_symbol,
            period,
            cadence_override='monthly',
        )
        try:
            archive = download_public_kline_archive(archive_root, spec)
        except FileNotFoundError:
            continue
        raw = read_archive_csv(archive, fallback_columns=_FUTURES_KLINE_COLUMNS)
        monthly_frames.append(_normalize_archive_5m(raw, symbol=symbol, year=year))
        available_months.append(month)
    if not monthly_frames:
        raise FileNotFoundError(f'{symbol} {year} 年没有可用的 USD-M 永续合约官方归档')
    expected_months = list(range(available_months[0], 13))
    if available_months != expected_months:
        missing = sorted(set(expected_months) - set(available_months))
        raise ValueError(f'{symbol} {year} 年官方归档缺少月份: {missing}')
    five_minute = pd.concat(monthly_frames).sort_index()
    _validate_five_minute_grid(five_minute, symbol=symbol, year=year)
    return rebuild_year_from_futures_5m(
        symbol,
        year,
        five_minute,
        data_dir=data_dir,
    )


def rebuild_year_from_futures_5m(
    symbol: str,
    year: int,
    five_minute: pd.DataFrame,
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> list[YearlyDataStatus]:
    """Validate one futures 5m frame and atomically replace all derived timeframes."""
    normalized = _normalize_ohlcv(five_minute)
    _validate_five_minute_grid(normalized, symbol=symbol, year=year)
    frames = {
        '5m': normalized,
        '15m': _resample_ohlcv(normalized, '15min'),
        '1h': _resample_ohlcv(normalized, '1h'),
        '4h': _resample_ohlcv(normalized, '4h'),
    }
    _atomic_write_year_package(
        data_dir=Path(data_dir),
        symbol=symbol,
        year=year,
        frames=frames,
    )
    return inspect_year_data(data_dir, symbol, year)


def _normalize_archive_5m(frame: pd.DataFrame, *, symbol: str, year: int) -> pd.DataFrame:
    required = {'open_time', 'open', 'high', 'low', 'close', 'volume'}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f'{symbol} {year} 年 K 线归档缺少字段: {missing}')
    numeric = frame.loc[:, ['open_time', 'open', 'high', 'low', 'close', 'volume']].apply(
        pd.to_numeric,
        errors='coerce',
    )
    timestamps = pd.to_datetime(numeric.pop('open_time'), unit='ms', utc=True, errors='coerce')
    normalized = numeric.rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume',
    })
    normalized.index = timestamps
    normalized.index.name = 'timestamp'
    if normalized.index.isna().any() or not np.isfinite(normalized.to_numpy(dtype=float)).all():
        raise ValueError(f'{symbol} {year} 年 K 线归档包含无效数值')
    return normalized


def _validate_five_minute_grid(frame: pd.DataFrame, *, symbol: str, year: int) -> None:
    normalized = _normalize_ohlcv(frame)
    if normalized.empty:
        raise ValueError(f'{symbol} {year} 年 5m K 线为空')
    if normalized.index.has_duplicates or not normalized.index.is_monotonic_increasing:
        raise ValueError(f'{symbol} {year} 年 5m 时间戳重复或未排序')
    start = pd.Timestamp(f'{year}-01-01', tz='UTC')
    end = pd.Timestamp(f'{year + 1}-01-01', tz='UTC')
    if normalized.index.min() < start or normalized.index.max() >= end:
        raise ValueError(f'{symbol} {year} 年 5m K 线越出所选年份')
    expected = pd.date_range(normalized.index.min(), end, freq='5min', inclusive='left')
    if not normalized.index.equals(expected):
        raise ValueError(f'{symbol} {year} 年 5m K 线在首个可用月份后存在缺口')
    valid_ohlc = (
        normalized['High'].ge(normalized[['Open', 'Close', 'Low']].max(axis=1))
        & normalized['Low'].le(normalized[['Open', 'Close', 'High']].min(axis=1))
        & normalized[['Open', 'High', 'Low', 'Close']].gt(0).all(axis=1)
        & normalized['Volume'].ge(0)
    )
    if not valid_ohlc.all():
        raise ValueError(f'{symbol} {year} 年 5m K 线 OHLCV 校验失败')


def _resample_ohlcv(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    resampled = frame.resample(rule, label='left', closed='left').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum',
    })
    return resampled.dropna(subset=['Open', 'High', 'Low', 'Close'])


def _atomic_write_year_package(
    *,
    data_dir: Path,
    symbol: str,
    year: int,
    frames: dict[str, pd.DataFrame],
) -> None:
    destinations = {
        timeframe: yearly_data_path(data_dir, symbol, timeframe, year)
        for timeframe in YEARLY_TIMEFRAMES
    }
    part_paths: dict[str, Path] = {}
    for timeframe, destination in destinations.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_name(f'{destination.name}.part')
        frames[timeframe].to_csv(part)
        part_paths[timeframe] = part
    manifest = yearly_source_path(data_dir, symbol, year)
    manifest_part = manifest.with_name(f'{manifest.name}.part')
    manifest_part.write_text(json.dumps({
        'source': MARKET_SOURCE,
        'symbol': symbol,
        'year': year,
        'base_timeframe': '5m',
        'derived_timeframes': ['15m', '1h', '4h'],
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    for timeframe in YEARLY_TIMEFRAMES:
        os.replace(part_paths[timeframe], destinations[timeframe])
    os.replace(manifest_part, manifest)


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
