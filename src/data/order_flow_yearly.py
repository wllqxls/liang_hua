"""Resumable annual BTC/ETH order-flow research packages."""

from __future__ import annotations

import calendar
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from src.data.order_flow import (
    FuturesKlineArchiveSpec,
    PublicArchiveSpec,
    SUPPORTED_SYMBOLS,
    download_public_archive,
    download_public_kline_archive,
    normalize_futures_klines,
    normalize_metrics,
    read_archive_csv,
)


ORDER_FLOW_RESEARCH_YEARS = (2024, 2025)
_KLINE_COLUMNS = (
    'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
    'quote_volume', 'count', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore',
)
ProgressCallback = Callable[..., None]


@dataclass(frozen=True, slots=True)
class AnnualArchiveTask:
    dataset: str
    symbol: str
    period: str


@dataclass(frozen=True, slots=True)
class OrderFlowYearStatus:
    symbol: str
    year: int
    state: str
    rows: int | None
    expected_rows: int
    missing_rows: int | None
    funding_rows: int | None
    file_size_kb: float | None
    error: str | None = None


def annual_order_flow_path(root: Path, *, symbol: str, year: int) -> Path:
    _validate_symbol_year(symbol, year, allow_holdout=True)
    return root / 'normalized' / 'order_flow_5m' / symbol / str(year) / f'{symbol}-order-flow-5m-{year}.csv'


def annual_funding_path(root: Path, *, symbol: str, year: int) -> Path:
    _validate_symbol_year(symbol, year, allow_holdout=True)
    return root / 'normalized' / 'fundingRate' / symbol / str(year) / f'{symbol}-fundingRate-{year}.csv'


def annual_archive_tasks(year: int) -> list[AnnualArchiveTask]:
    _validate_year(year)
    tasks: list[AnnualArchiveTask] = []
    days = _year_days(year)
    for symbol in SUPPORTED_SYMBOLS:
        for month in range(1, 13):
            period = f'{year}-{month:02d}'
            tasks.append(AnnualArchiveTask('klines_5m', symbol, period))
            tasks.append(AnnualArchiveTask('fundingRate', symbol, period))
        tasks.extend(AnnualArchiveTask('metrics', symbol, day) for day in days)
    return tasks


def fetch_order_flow_year(
    *,
    year: int,
    root: Path,
    progress: ProgressCallback | None = None,
    max_workers: int = 8,
) -> list[OrderFlowYearStatus]:
    """Download verified public archives and atomically build annual files."""
    _validate_year(year)
    callback = progress or (lambda **_: None)
    tasks = annual_archive_tasks(year)
    callback(stage='下载官方归档', completed=0, total=len(tasks))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_download_task, root, task): task for task in tasks}
        completed = 0
        for future in as_completed(futures):
            future.result()
            completed += 1
            callback(stage='下载官方归档', completed=completed, total=len(tasks))

    for index, symbol in enumerate(SUPPORTED_SYMBOLS, start=1):
        callback(
            stage=f'合并并审计 {symbol}',
            completed=len(tasks),
            total=len(tasks),
        )
        _build_symbol_year(root=root, symbol=symbol, year=year)
        callback(
            stage=f'已生成 {index}/{len(SUPPORTED_SYMBOLS)} 个年度文件',
            completed=len(tasks),
            total=len(tasks),
        )
    return inspect_order_flow_year(root=root, year=year)


def inspect_order_flow_year(*, root: Path, year: int) -> list[OrderFlowYearStatus]:
    _validate_symbol_year(SUPPORTED_SYMBOLS[0], year, allow_holdout=True)
    expected = _expected_rows(year)
    return [_inspect_symbol(root, symbol, year, expected) for symbol in SUPPORTED_SYMBOLS]


def _download_task(root: Path, task: AnnualArchiveTask) -> Path:
    if task.dataset == 'klines_5m':
        return download_public_kline_archive(
            root,
            FuturesKlineArchiveSpec(
                task.symbol,
                task.period,
                cadence_override='monthly',
            ),
        )
    return download_public_archive(
        root,
        PublicArchiveSpec(task.dataset, task.symbol, task.period),
    )


def _build_symbol_year(*, root: Path, symbol: str, year: int) -> None:
    kline_days: list[pd.DataFrame] = []
    metrics_days: list[pd.DataFrame] = []
    funding_months: list[pd.DataFrame] = []

    for month in range(1, 13):
        period = f'{year}-{month:02d}'
        kline_spec = FuturesKlineArchiveSpec(symbol, period, cadence_override='monthly')
        kline_archive = (
            root / 'raw' / 'klines_5m' / symbol / str(year) / kline_spec.filename
        )
        month_frame = read_archive_csv(kline_archive, fallback_columns=_KLINE_COLUMNS)
        open_times = pd.to_datetime(month_frame['open_time'], unit='ms', utc=True, errors='coerce')
        if open_times.isna().any():
            raise ValueError(f'{symbol} {period} enhanced kline timestamp is invalid')
        for day_value, day_frame in month_frame.groupby(open_times.dt.strftime('%Y-%m-%d')):
            normalized, audit = normalize_futures_klines(
                day_frame,
                symbol=symbol,
                day=str(day_value),
            )
            if audit.status != 'PASS':
                raise ValueError(f'{symbol} {day_value} enhanced kline audit failed')
            kline_days.append(normalized)

        funding_spec = PublicArchiveSpec('fundingRate', symbol, period)
        funding_frame = read_archive_csv(
            root / 'raw' / 'fundingRate' / symbol / str(year) / funding_spec.filename
        )
        funding_months.append(_normalize_funding(funding_frame, symbol=symbol, year=year))

    for day_value in _year_days(year):
        metrics_spec = PublicArchiveSpec('metrics', symbol, day_value)
        metrics_frame = read_archive_csv(
            root / 'raw' / 'metrics' / symbol / str(year) / metrics_spec.filename
        )
        normalized, audit = normalize_metrics(metrics_frame, symbol=symbol, day=day_value)
        if audit.status != 'PASS':
            raise ValueError(f'{symbol} {day_value} metrics audit failed')
        metrics_days.append(normalized.drop(columns=['symbol']))

    klines = pd.concat(kline_days).sort_index()
    metrics = pd.concat(metrics_days).sort_index()
    expected_index = pd.date_range(
        f'{year}-01-01', f'{year + 1}-01-01', freq='5min', inclusive='left', tz='UTC'
    )
    if klines.index.duplicated().any() or not klines.index.equals(expected_index):
        raise ValueError(f'{symbol} annual enhanced kline grid is incomplete')
    if metrics.index.duplicated().any() or not metrics.index.equals(expected_index):
        raise ValueError(f'{symbol} annual metrics grid is incomplete')
    annual = klines.join(metrics, how='left', validate='one_to_one')
    if annual.isna().any().any():
        raise ValueError(f'{symbol} annual order-flow join contains missing values')

    funding = pd.concat(funding_months).sort_index()
    if funding.index.duplicated().any():
        raise ValueError(f'{symbol} annual funding data contains duplicate timestamps')
    if funding.empty or funding.index.year.min() != year or funding.index.year.max() != year:
        raise ValueError(f'{symbol} annual funding data is incomplete')

    _atomic_write_csv(
        annual,
        annual_order_flow_path(root, symbol=symbol, year=year),
    )
    _atomic_write_csv(
        funding,
        annual_funding_path(root, symbol=symbol, year=year),
    )


def _normalize_funding(frame: pd.DataFrame, *, symbol: str, year: int) -> pd.DataFrame:
    required = {'calc_time', 'funding_interval_hours', 'last_funding_rate'}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f'fundingRate is missing required columns: {", ".join(sorted(missing))}')
    normalized = frame.loc[:, sorted(required)].copy()
    normalized['timestamp'] = pd.to_datetime(
        normalized['calc_time'], unit='ms', utc=True, errors='coerce'
    )
    normalized['funding_interval_hours'] = pd.to_numeric(
        normalized['funding_interval_hours'], errors='coerce'
    )
    normalized['last_funding_rate'] = pd.to_numeric(
        normalized['last_funding_rate'], errors='coerce'
    )
    normalized = normalized.loc[
        normalized['timestamp'].notna()
        & normalized['timestamp'].dt.year.eq(year)
        & normalized['funding_interval_hours'].gt(0)
        & normalized['last_funding_rate'].notna()
    ].set_index('timestamp').sort_index()
    normalized = normalized.drop(columns=['calc_time'])
    normalized.insert(0, 'symbol', symbol)
    return normalized


def _inspect_symbol(root: Path, symbol: str, year: int, expected: int) -> OrderFlowYearStatus:
    data_path = annual_order_flow_path(root, symbol=symbol, year=year)
    funding_path = annual_funding_path(root, symbol=symbol, year=year)
    if not data_path.exists() and not funding_path.exists():
        return OrderFlowYearStatus(symbol, year, 'missing', None, expected, None, None, None)
    try:
        rows, missing = _inspect_annual_grid(data_path, year)
        funding_rows = _inspect_funding(funding_path, year)
        size = sum(path.stat().st_size for path in (data_path, funding_path) if path.exists()) / 1024
        state = 'complete' if rows == expected and missing == 0 and funding_rows > 0 else 'partial'
        return OrderFlowYearStatus(
            symbol, year, state, rows, expected, missing, funding_rows, round(size, 1)
        )
    except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        return OrderFlowYearStatus(
            symbol, year, 'invalid', None, expected, None, None, None, str(exc)
        )


def _inspect_annual_grid(path: Path, year: int) -> tuple[int, int]:
    required = {
        'timestamp',
        'symbol',
        'close',
        'volume',
        'taker_buy_volume',
        'taker_sell_volume',
        'order_flow_imbalance',
        'sum_open_interest',
    }
    columns = set(pd.read_csv(path, nrows=0).columns)
    missing_columns = required.difference(columns)
    if missing_columns:
        raise ValueError(f'annual order-flow columns are missing: {", ".join(sorted(missing_columns))}')
    frame = pd.read_csv(path, usecols=['timestamp'])
    timestamps = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce')
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError('5m timestamp is invalid or duplicated')
    expected = pd.date_range(
        f'{year}-01-01', f'{year + 1}-01-01', freq='5min', inclusive='left', tz='UTC'
    )
    actual = pd.DatetimeIndex(timestamps).sort_values()
    return len(actual), len(expected.difference(actual))


def _inspect_funding(path: Path, year: int) -> int:
    columns = set(pd.read_csv(path, nrows=0).columns)
    if not {'timestamp', 'symbol', 'last_funding_rate'}.issubset(columns):
        raise ValueError('annual funding columns are missing')
    frame = pd.read_csv(path, usecols=['timestamp'])
    timestamps = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce')
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError('funding timestamp is invalid or duplicated')
    if not timestamps.dt.year.eq(year).all():
        raise ValueError('funding timestamp is outside selected year')
    return len(frame)


def _atomic_write_csv(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f'{destination.suffix}.part')
    frame.to_csv(temporary, index_label='timestamp')
    os.replace(temporary, destination)


def _year_days(year: int) -> list[str]:
    start = date(year, 1, 1)
    return [item.strftime('%Y-%m-%d') for item in pd.date_range(start, periods=366 if calendar.isleap(year) else 365)]


def _expected_rows(year: int) -> int:
    return (366 if calendar.isleap(year) else 365) * 288


def _validate_year(year: int) -> None:
    if year not in ORDER_FLOW_RESEARCH_YEARS:
        raise ValueError('订单流年度下载只开放 2024/2025，2026 为保留期')


def _validate_symbol_year(symbol: str, year: int, *, allow_holdout: bool) -> None:
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {symbol}')
    if allow_holdout:
        if year < 2017 or year > 2100:
            raise ValueError('year must be between 2017 and 2100')
    else:
        _validate_year(year)
