"""Resumable annual BTC/ETH order-flow research packages."""

from __future__ import annotations

import calendar
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.order_flow import (
    FuturesKlineArchiveSpec,
    PublicArchiveSpec,
    SUPPORTED_SYMBOLS,
    download_public_archive,
    download_public_kline_archive,
    normalize_futures_klines,
    read_archive_csv,
)


ORDER_FLOW_RESEARCH_YEARS = (2023, 2024, 2025)
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
    metrics_missing_rows: int | None = None
    metrics_coverage_pct: float | None = None


@dataclass(frozen=True, slots=True)
class AnnualMetricsAudit:
    symbol: str
    year: int
    raw_rows: int
    invalid_rows: int
    out_of_year_rows: int
    duplicate_buckets: int
    missing_rows: int
    coverage_pct: float


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
        metrics_days.append(metrics_frame)

    klines = pd.concat(kline_days).sort_index()
    metrics, metrics_audit = normalize_annual_metrics(
        pd.concat(metrics_days, ignore_index=True),
        symbol=symbol,
        year=year,
    )
    expected_index = pd.date_range(
        f'{year}-01-01', f'{year + 1}-01-01', freq='5min', inclusive='left', tz='UTC'
    )
    if klines.index.duplicated().any() or not klines.index.equals(expected_index):
        raise ValueError(f'{symbol} annual enhanced kline grid is incomplete')
    if metrics_audit.coverage_pct < 99.0:
        raise ValueError(
            f'{symbol} annual metrics coverage is only '
            f'{metrics_audit.coverage_pct:.4f}%'
        )
    annual = klines.join(metrics, how='left', validate='one_to_one')
    if not annual.index.equals(expected_index):
        raise ValueError(f'{symbol} annual order-flow grid is incomplete')
    if annual.loc[annual['metrics_available'], 'sum_open_interest'].isna().any():
        raise ValueError(f'{symbol} available metrics rows contain missing values')

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


def normalize_annual_metrics(
    frame: pd.DataFrame,
    *,
    symbol: str,
    year: int,
) -> tuple[pd.DataFrame, AnnualMetricsAudit]:
    """Align official metrics to UTC 5m buckets and preserve real annual gaps."""
    _validate_symbol_year(symbol, year, allow_holdout=True)
    required = (
        'create_time',
        'symbol',
        'sum_open_interest',
        'sum_open_interest_value',
        'count_toptrader_long_short_ratio',
        'sum_toptrader_long_short_ratio',
        'count_long_short_ratio',
        'sum_taker_long_short_vol_ratio',
    )
    missing_columns = [column for column in required if column not in frame]
    if missing_columns:
        raise ValueError(
            f'metrics is missing required columns: {", ".join(missing_columns)}'
        )
    working = frame.loc[:, list(required)].copy()
    timestamps = pd.to_datetime(working['create_time'], utc=True, errors='coerce')
    numeric_columns = list(required[2:])
    for column in numeric_columns:
        working[column] = pd.to_numeric(working[column], errors='coerce')
    finite_numeric = np.isfinite(
        working.loc[:, numeric_columns].to_numpy(dtype=float)
    ).all(axis=1)
    valid = (
        timestamps.notna()
        & working['symbol'].eq(symbol)
        & finite_numeric
        & working['sum_open_interest'].ge(0)
        & working['sum_open_interest_value'].ge(0)
    )
    invalid_rows = int((~valid).sum())
    valid_frame = working.loc[valid].copy()
    valid_frame['timestamp'] = timestamps.loc[valid].dt.floor('5min')
    start = pd.Timestamp(f'{year}-01-01', tz='UTC')
    end = pd.Timestamp(f'{year + 1}-01-01', tz='UTC')
    in_year = valid_frame['timestamp'].ge(start) & valid_frame['timestamp'].lt(end)
    out_of_year_rows = int((~in_year).sum())
    annual = valid_frame.loc[in_year].copy().sort_values('timestamp', kind='stable')
    duplicate_buckets = int(annual['timestamp'].duplicated(keep='last').sum())
    annual = annual.drop_duplicates('timestamp', keep='last').set_index('timestamp')
    annual = annual.drop(columns=['create_time', 'symbol'])
    expected_index = pd.date_range(start, end, freq='5min', inclusive='left')
    annual = annual.reindex(expected_index)
    metrics_available = annual[numeric_columns].notna().all(axis=1)
    annual.insert(0, 'metrics_available', metrics_available)
    missing_rows = int((~metrics_available).sum())
    coverage_pct = round(100.0 * (len(annual) - missing_rows) / len(annual), 6)
    audit = AnnualMetricsAudit(
        symbol=symbol,
        year=year,
        raw_rows=len(frame),
        invalid_rows=invalid_rows,
        out_of_year_rows=out_of_year_rows,
        duplicate_buckets=duplicate_buckets,
        missing_rows=missing_rows,
        coverage_pct=coverage_pct,
    )
    return annual, audit


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
        rows, missing, metrics_missing = _inspect_annual_grid(data_path, year)
        funding_rows = _inspect_funding(funding_path, year)
        size = sum(path.stat().st_size for path in (data_path, funding_path) if path.exists()) / 1024
        metrics_coverage = round(100.0 * (rows - metrics_missing) / rows, 6) if rows else 0.0
        if rows == expected and missing == 0 and metrics_missing == 0 and funding_rows > 0:
            state = 'complete'
        elif rows == expected and missing == 0 and metrics_coverage >= 99.0 and funding_rows > 0:
            state = 'usable'
        else:
            state = 'partial'
        return OrderFlowYearStatus(
            symbol=symbol,
            year=year,
            state=state,
            rows=rows,
            expected_rows=expected,
            missing_rows=missing,
            funding_rows=funding_rows,
            file_size_kb=round(size, 1),
            metrics_missing_rows=metrics_missing,
            metrics_coverage_pct=metrics_coverage,
        )
    except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        return OrderFlowYearStatus(
            symbol, year, 'invalid', None, expected, None, None, None, str(exc)
        )


def _inspect_annual_grid(path: Path, year: int) -> tuple[int, int, int]:
    required = {
        'timestamp',
        'symbol',
        'close',
        'volume',
        'taker_buy_volume',
        'taker_sell_volume',
        'order_flow_imbalance',
        'sum_open_interest',
        'metrics_available',
    }
    columns = set(pd.read_csv(path, nrows=0).columns)
    missing_columns = required.difference(columns)
    if missing_columns:
        raise ValueError(f'annual order-flow columns are missing: {", ".join(sorted(missing_columns))}')
    frame = pd.read_csv(path, usecols=['timestamp', 'metrics_available'])
    timestamps = pd.to_datetime(
        frame['timestamp'], utc=True, errors='coerce', format='mixed'
    )
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError('5m timestamp is invalid or duplicated')
    expected = pd.date_range(
        f'{year}-01-01', f'{year + 1}-01-01', freq='5min', inclusive='left', tz='UTC'
    )
    actual = pd.DatetimeIndex(timestamps).sort_values()
    availability = frame['metrics_available']
    if availability.dtype != bool:
        availability = availability.astype(str).str.lower().map({'true': True, 'false': False})
    if availability.isna().any():
        raise ValueError('metrics_available contains invalid values')
    metrics_missing = int((~availability.astype(bool)).sum())
    return len(actual), len(expected.difference(actual)), metrics_missing


def _inspect_funding(path: Path, year: int) -> int:
    columns = set(pd.read_csv(path, nrows=0).columns)
    if not {'timestamp', 'symbol', 'last_funding_rate'}.issubset(columns):
        raise ValueError('annual funding columns are missing')
    frame = pd.read_csv(path, usecols=['timestamp'])
    timestamps = pd.to_datetime(
        frame['timestamp'], utc=True, errors='coerce', format='mixed'
    )
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
        raise ValueError('订单流年度下载只开放 2023/2024/2025，2026 为未结束年度')


def _validate_symbol_year(symbol: str, year: int, *, allow_holdout: bool) -> None:
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {symbol}')
    if allow_holdout:
        if year < 2017 or year > 2100:
            raise ValueError('year must be between 2017 and 2100')
    else:
        _validate_year(year)
