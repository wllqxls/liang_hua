"""Download, normalize, and audit public Binance USD-M order-flow archives."""

from __future__ import annotations

import hashlib
import math
import os
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd


BINANCE_DATA_BASE_URL = 'https://data.binance.vision/data/futures/um'
ORDER_FLOW_ROOT = Path('data/order_flow/binance_um')
SUPPORTED_SYMBOLS = ('BTCUSDT', 'ETHUSDT')
SUPPORTED_DATASETS = ('aggTrades', 'metrics', 'fundingRate', 'bookDepth')
_DAILY_DATASETS = {'aggTrades', 'metrics', 'bookDepth'}
_AGG_TRADE_COLUMNS = (
    'agg_trade_id',
    'price',
    'quantity',
    'first_trade_id',
    'last_trade_id',
    'transact_time',
    'is_buyer_maker',
)
_FUTURES_KLINE_COLUMNS = (
    'open_time',
    'open',
    'high',
    'low',
    'close',
    'volume',
    'close_time',
    'quote_volume',
    'count',
    'taker_buy_volume',
    'taker_buy_quote_volume',
    'ignore',
)
_NORMALIZED_COLUMNS = (
    'symbol',
    'aggregate_trade_count',
    'base_volume',
    'quote_volume',
    'taker_buy_base_volume',
    'taker_sell_base_volume',
    'taker_buy_quote_volume',
    'taker_sell_quote_volume',
    'signed_base_volume',
    'order_flow_imbalance',
)


@dataclass(frozen=True, slots=True)
class PublicArchiveSpec:
    dataset: Literal['aggTrades', 'metrics', 'fundingRate', 'bookDepth'] | str
    symbol: str
    period: str
    cadence_override: Literal['daily', 'monthly'] | str | None = None

    @property
    def cadence(self) -> str:
        if self.cadence_override is not None:
            return self.cadence_override
        return 'daily' if self.dataset in _DAILY_DATASETS else 'monthly'

    @property
    def filename(self) -> str:
        return f'{self.symbol}-{self.dataset}-{self.period}.zip'

    @property
    def url(self) -> str:
        return (
            f'{BINANCE_DATA_BASE_URL}/{self.cadence}/{self.dataset}/'
            f'{self.symbol}/{self.filename}'
        )

    @property
    def checksum_url(self) -> str:
        return f'{self.url}.CHECKSUM'


@dataclass(frozen=True, slots=True)
class FuturesKlineArchiveSpec:
    symbol: str
    day: str
    interval: str = '5m'
    cadence_override: Literal['daily', 'monthly'] | str | None = None

    @property
    def cadence(self) -> str:
        if self.cadence_override is not None:
            return self.cadence_override
        return 'daily'

    @property
    def filename(self) -> str:
        return f'{self.symbol}-{self.interval}-{self.day}.zip'

    @property
    def url(self) -> str:
        return (
            f'{BINANCE_DATA_BASE_URL}/{self.cadence}/klines/{self.symbol}/'
            f'{self.interval}/{self.filename}'
        )

    @property
    def checksum_url(self) -> str:
        return f'{self.url}.CHECKSUM'


@dataclass(frozen=True, slots=True)
class AggTradeAudit:
    symbol: str
    day: str
    raw_rows: int
    duplicate_trade_ids: int
    invalid_rows: int
    out_of_day_rows: int
    populated_five_minute_buckets: int
    missing_five_minute_buckets: int
    maximum_volume_conservation_error: float
    first_timestamp: pd.Timestamp | None
    last_timestamp: pd.Timestamp | None
    status: str


@dataclass(frozen=True, slots=True)
class MetricsAudit:
    symbol: str
    day: str
    rows: int
    duplicate_timestamps: int
    invalid_rows: int
    out_of_day_rows: int
    missing_five_minute_timestamps: int
    status: str


@dataclass(frozen=True, slots=True)
class KlineOrderFlowAudit:
    symbol: str
    day: str
    rows: int
    duplicate_timestamps: int
    invalid_rows: int
    out_of_day_rows: int
    missing_five_minute_timestamps: int
    maximum_base_volume_error: float
    maximum_quote_volume_error: float
    status: str


def validate_archive_spec(spec: PublicArchiveSpec) -> None:
    if spec.dataset not in SUPPORTED_DATASETS:
        raise ValueError(f'unsupported order-flow dataset: {spec.dataset}')
    if spec.symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {spec.symbol}')
    if spec.cadence not in {'daily', 'monthly'}:
        raise ValueError(f'unsupported archive cadence: {spec.cadence}')
    expected_length = 10 if spec.cadence == 'daily' else 7
    try:
        parsed = pd.Timestamp(spec.period)
    except ValueError:
        raise ValueError(f'invalid archive period: {spec.period}') from None
    if len(spec.period) != expected_length:
        raise ValueError(
            f'{spec.dataset} period must use '
            f'{"YYYY-MM-DD" if expected_length == 10 else "YYYY-MM"}'
        )
    if spec.cadence == 'monthly' and parsed.day != 1:
        raise ValueError('monthly archive period must identify one month')


def archive_path(root: Path, spec: PublicArchiveSpec) -> Path:
    validate_archive_spec(spec)
    year = spec.period[:4]
    return root / 'raw' / spec.dataset / spec.symbol / year / spec.filename


def normalized_agg_trade_path(root: Path, *, symbol: str, day: str) -> Path:
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {symbol}')
    parsed_day = _parse_day(day)
    return (
        root
        / 'normalized'
        / 'aggTrades_5m'
        / symbol
        / str(parsed_day.year)
        / f'{symbol}-aggTrades-5m-{day}.csv'
    )


def normalized_metrics_path(root: Path, *, symbol: str, day: str) -> Path:
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {symbol}')
    parsed_day = _parse_day(day)
    return (
        root
        / 'normalized'
        / 'metrics'
        / symbol
        / str(parsed_day.year)
        / f'{symbol}-metrics-{day}.csv'
    )


def kline_archive_path(root: Path, spec: FuturesKlineArchiveSpec) -> Path:
    _validate_kline_spec(spec)
    return (
        root
        / 'raw'
        / 'klines_5m'
        / spec.symbol
        / spec.day[:4]
        / spec.filename
    )


def normalized_kline_path(root: Path, *, symbol: str, day: str) -> Path:
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {symbol}')
    parsed_day = _parse_day(day)
    return (
        root
        / 'normalized'
        / 'klines_5m'
        / symbol
        / str(parsed_day.year)
        / f'{symbol}-order-flow-5m-{day}.csv'
    )


def download_public_archive(root: Path, spec: PublicArchiveSpec) -> Path:
    """Download one archive and verify its official SHA-256 sidecar."""
    destination = archive_path(root, spec)
    return _download_verified_archive(
        url=spec.url,
        checksum_url=spec.checksum_url,
        destination=destination,
    )


def _download_verified_archive(
    *,
    url: str,
    checksum_url: str,
    destination: Path,
) -> Path:
    checksum_path = destination.with_name(f'{destination.name}.CHECKSUM')
    if destination.exists() and checksum_path.exists():
        expected = parse_checksum(checksum_path.read_text(encoding='utf-8'))
        if sha256_file(destination) == expected:
            return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(f'{destination.name}.part')
    maximum_attempts = 5
    for attempt in range(1, maximum_attempts + 1):
        try:
            with urllib.request.urlopen(checksum_url, timeout=30) as response:
                checksum_content = response.read()
            expected = parse_checksum(checksum_content.decode('utf-8'))
            with urllib.request.urlopen(url, timeout=60) as response, part_path.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            actual = sha256_file(part_path)
            if actual != expected:
                raise ValueError(
                    f'checksum mismatch for {destination.name}: '
                    f'expected {expected}, got {actual}'
                )
            checksum_path.write_bytes(checksum_content)
            os.replace(part_path, destination)
            return destination
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise FileNotFoundError(f'official archive unavailable: {url}') from exc
            if attempt == maximum_attempts:
                raise RuntimeError(
                    f'download failed after {maximum_attempts} attempts: {destination.name}'
                ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            if attempt == maximum_attempts:
                raise RuntimeError(
                    f'download failed after {maximum_attempts} attempts: {destination.name}'
                ) from exc
        time.sleep(0.5 * (2 ** (attempt - 1)))
    raise RuntimeError(f'unreachable download state: {destination.name}')


def download_public_kline_archive(
    root: Path,
    spec: FuturesKlineArchiveSpec,
) -> Path:
    """Download one enhanced futures kline day with checksum validation."""
    destination = kline_archive_path(root, spec)
    return _download_verified_archive(
        url=spec.url,
        checksum_url=spec.checksum_url,
        destination=destination,
    )


def public_archive_size(spec: PublicArchiveSpec) -> int | None:
    """Return the official archive size, or None when it is unavailable."""
    validate_archive_spec(spec)
    return _head_content_length(spec.url)


def public_kline_archive_size(spec: FuturesKlineArchiveSpec) -> int | None:
    _validate_kline_spec(spec)
    return _head_content_length(spec.url)


def _head_content_length(url: str) -> int | None:
    request = urllib.request.Request(url, method='HEAD')
    last_error: urllib.error.URLError | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content_length = response.headers.get('Content-Length')
            return int(content_length) if content_length is not None else 0
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        except urllib.error.URLError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError('unreachable HEAD retry state')


def estimate_monthly_agg_trade_bytes(
    *,
    symbols: tuple[str, ...] = SUPPORTED_SYMBOLS,
    years: tuple[int, ...] = (2024, 2025),
) -> int:
    """Sum official monthly archive sizes without downloading their bodies."""
    total = 0
    for symbol in symbols:
        for year in years:
            for month in range(1, 13):
                spec = PublicArchiveSpec(
                    'aggTrades',
                    symbol,
                    f'{year}-{month:02d}',
                    cadence_override='monthly',
                )
                size = public_archive_size(spec)
                if size is None:
                    raise FileNotFoundError(f'archive not found: {spec.url}')
                total += size
    return total


def parse_checksum(content: str) -> str:
    fields = content.strip().split()
    if not fields or len(fields[0]) != 64:
        raise ValueError('invalid Binance checksum content')
    checksum = fields[0].lower()
    if any(character not in '0123456789abcdef' for character in checksum):
        raise ValueError('invalid Binance checksum content')
    return checksum


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_archive_csv(path: Path, *, fallback_columns: tuple[str, ...] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f'archive not found: {path}')
    if not zipfile.is_zipfile(path):
        raise ValueError(f'archive is not a valid ZIP: {path}')
    frame = pd.read_csv(path)
    if fallback_columns is not None and not set(fallback_columns).issubset(frame.columns):
        frame = pd.read_csv(path, header=None, names=list(fallback_columns))
    return frame


def normalize_agg_trades(
    frame: pd.DataFrame,
    *,
    symbol: str,
    day: str,
) -> tuple[pd.DataFrame, AggTradeAudit]:
    """Aggregate signed trades into complete UTC 5m buckets and audit them."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {symbol}')
    parsed_day = _parse_day(day)
    missing = [column for column in _AGG_TRADE_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f'aggTrades is missing required columns: {", ".join(missing)}')
    working = frame.loc[:, _AGG_TRADE_COLUMNS].copy()
    numeric_columns = (
        'agg_trade_id',
        'price',
        'quantity',
        'transact_time',
    )
    for column in numeric_columns:
        working[column] = pd.to_numeric(working[column], errors='coerce')
    maker = working['is_buyer_maker'].map(_parse_bool)
    timestamps = pd.to_datetime(working['transact_time'], unit='ms', utc=True, errors='coerce')
    finite_numeric = np.isfinite(working.loc[:, numeric_columns].to_numpy(dtype=float)).all(axis=1)
    valid = (
        finite_numeric
        & working['price'].gt(0)
        & working['quantity'].gt(0)
        & maker.notna()
        & timestamps.notna()
    )
    invalid_rows = int((~valid).sum())
    valid_frame = working.loc[valid].copy()
    valid_frame['is_buyer_maker'] = maker.loc[valid].astype(bool)
    valid_frame['timestamp'] = timestamps.loc[valid]
    start = pd.Timestamp(parsed_day, tz='UTC')
    end = start + pd.Timedelta(days=1)
    in_day = valid_frame['timestamp'].ge(start) & valid_frame['timestamp'].lt(end)
    out_of_day_rows = int((~in_day).sum())
    day_frame = valid_frame.loc[in_day].copy()
    duplicate_ids = int(day_frame['agg_trade_id'].duplicated().sum())
    day_frame['quote_volume'] = day_frame['price'] * day_frame['quantity']
    day_frame['timestamp'] = day_frame['timestamp'].dt.floor('5min')
    day_frame['taker_buy_base_volume'] = np.where(
        ~day_frame['is_buyer_maker'],
        day_frame['quantity'],
        0.0,
    )
    day_frame['taker_sell_base_volume'] = np.where(
        day_frame['is_buyer_maker'],
        day_frame['quantity'],
        0.0,
    )
    day_frame['taker_buy_quote_volume'] = np.where(
        ~day_frame['is_buyer_maker'],
        day_frame['quote_volume'],
        0.0,
    )
    day_frame['taker_sell_quote_volume'] = np.where(
        day_frame['is_buyer_maker'],
        day_frame['quote_volume'],
        0.0,
    )
    grouped = day_frame.groupby('timestamp').agg(
        aggregate_trade_count=('agg_trade_id', 'size'),
        base_volume=('quantity', 'sum'),
        quote_volume=('quote_volume', 'sum'),
        taker_buy_base_volume=('taker_buy_base_volume', 'sum'),
        taker_sell_base_volume=('taker_sell_base_volume', 'sum'),
        taker_buy_quote_volume=('taker_buy_quote_volume', 'sum'),
        taker_sell_quote_volume=('taker_sell_quote_volume', 'sum'),
    )
    populated_buckets = len(grouped)
    full_index = pd.date_range(start, end, freq='5min', inclusive='left')
    normalized = grouped.reindex(full_index, fill_value=0.0)
    normalized.insert(0, 'symbol', symbol)
    normalized['aggregate_trade_count'] = normalized['aggregate_trade_count'].astype(int)
    normalized['signed_base_volume'] = (
        normalized['taker_buy_base_volume'] - normalized['taker_sell_base_volume']
    )
    normalized['order_flow_imbalance'] = np.where(
        normalized['base_volume'] > 0,
        normalized['signed_base_volume'] / normalized['base_volume'],
        0.0,
    )
    normalized = normalized.loc[:, _NORMALIZED_COLUMNS]
    volume_error = (
        normalized['taker_buy_base_volume']
        + normalized['taker_sell_base_volume']
        - normalized['base_volume']
    ).abs()
    maximum_error = float(volume_error.max()) if not volume_error.empty else math.nan
    status = 'PASS'
    if invalid_rows or out_of_day_rows or duplicate_ids or populated_buckets != 288:
        status = 'FAIL'
    if not math.isfinite(maximum_error) or maximum_error > 1e-9:
        status = 'FAIL'
    audit = AggTradeAudit(
        symbol=symbol,
        day=day,
        raw_rows=len(frame),
        duplicate_trade_ids=duplicate_ids,
        invalid_rows=invalid_rows,
        out_of_day_rows=out_of_day_rows,
        populated_five_minute_buckets=populated_buckets,
        missing_five_minute_buckets=288 - populated_buckets,
        maximum_volume_conservation_error=maximum_error,
        first_timestamp=(day_frame['timestamp'].min() if not day_frame.empty else None),
        last_timestamp=(day_frame['timestamp'].max() if not day_frame.empty else None),
        status=status,
    )
    return normalized, audit


def normalize_agg_trades_archive(
    archive: Path,
    *,
    symbol: str,
    day: str,
    output_root: Path,
) -> tuple[Path, AggTradeAudit]:
    frame = read_archive_csv(archive, fallback_columns=_AGG_TRADE_COLUMNS)
    normalized, audit = normalize_agg_trades(frame, symbol=symbol, day=day)
    destination = normalized_agg_trade_path(output_root, symbol=symbol, day=day)
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(destination, index_label='timestamp')
    return destination, audit


def normalize_futures_klines(
    frame: pd.DataFrame,
    *,
    symbol: str,
    day: str,
) -> tuple[pd.DataFrame, KlineOrderFlowAudit]:
    """Normalize enhanced 5m klines into signed order-flow fields."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {symbol}')
    parsed_day = _parse_day(day)
    missing = [column for column in _FUTURES_KLINE_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f'klines is missing required columns: {", ".join(missing)}')
    working = frame.loc[:, list(_FUTURES_KLINE_COLUMNS)].copy()
    numeric_columns = [column for column in _FUTURES_KLINE_COLUMNS if column != 'ignore']
    for column in numeric_columns:
        working[column] = pd.to_numeric(working[column], errors='coerce')
    timestamps = pd.to_datetime(working['open_time'], unit='ms', utc=True, errors='coerce')
    finite_numeric = np.isfinite(
        working.loc[:, numeric_columns].to_numpy(dtype=float)
    ).all(axis=1)
    valid = (
        timestamps.notna()
        & finite_numeric
        & working[['open', 'high', 'low', 'close']].gt(0).all(axis=1)
        & working[['volume', 'quote_volume', 'count']].ge(0).all(axis=1)
        & working[['taker_buy_volume', 'taker_buy_quote_volume']].ge(0).all(axis=1)
        & working['taker_buy_volume'].le(working['volume'] + 1e-9)
        & working['taker_buy_quote_volume'].le(working['quote_volume'] + 1e-6)
    )
    invalid_rows = int((~valid).sum())
    valid_frame = working.loc[valid].copy()
    valid_frame['timestamp'] = timestamps.loc[valid]
    start = pd.Timestamp(parsed_day, tz='UTC')
    end = start + pd.Timedelta(days=1)
    in_day = valid_frame['timestamp'].ge(start) & valid_frame['timestamp'].lt(end)
    out_of_day_rows = int((~in_day).sum())
    day_frame = valid_frame.loc[in_day].copy()
    duplicate_timestamps = int(day_frame['timestamp'].duplicated().sum())
    day_frame['taker_sell_volume'] = (
        day_frame['volume'] - day_frame['taker_buy_volume']
    )
    day_frame['taker_sell_quote_volume'] = (
        day_frame['quote_volume'] - day_frame['taker_buy_quote_volume']
    )
    day_frame['signed_base_volume'] = (
        day_frame['taker_buy_volume'] - day_frame['taker_sell_volume']
    )
    day_frame['order_flow_imbalance'] = np.where(
        day_frame['volume'] > 0,
        day_frame['signed_base_volume'] / day_frame['volume'],
        0.0,
    )
    output_columns = [
        'open',
        'high',
        'low',
        'close',
        'volume',
        'quote_volume',
        'count',
        'taker_buy_volume',
        'taker_sell_volume',
        'taker_buy_quote_volume',
        'taker_sell_quote_volume',
        'signed_base_volume',
        'order_flow_imbalance',
    ]
    normalized = day_frame.set_index('timestamp').sort_index().loc[:, output_columns]
    normalized.insert(0, 'symbol', symbol)
    expected_index = pd.date_range(start, end, freq='5min', inclusive='left')
    missing_timestamps = len(expected_index.difference(normalized.index))
    base_error = (
        normalized['taker_buy_volume']
        + normalized['taker_sell_volume']
        - normalized['volume']
    ).abs()
    quote_error = (
        normalized['taker_buy_quote_volume']
        + normalized['taker_sell_quote_volume']
        - normalized['quote_volume']
    ).abs()
    maximum_base_error = float(base_error.max()) if not base_error.empty else math.nan
    maximum_quote_error = float(quote_error.max()) if not quote_error.empty else math.nan
    status = 'PASS'
    if invalid_rows or out_of_day_rows or duplicate_timestamps or missing_timestamps:
        status = 'FAIL'
    if (
        not math.isfinite(maximum_base_error)
        or not math.isfinite(maximum_quote_error)
        or maximum_base_error > 1e-9
        or maximum_quote_error > 1e-6
    ):
        status = 'FAIL'
    audit = KlineOrderFlowAudit(
        symbol=symbol,
        day=day,
        rows=len(frame),
        duplicate_timestamps=duplicate_timestamps,
        invalid_rows=invalid_rows,
        out_of_day_rows=out_of_day_rows,
        missing_five_minute_timestamps=missing_timestamps,
        maximum_base_volume_error=maximum_base_error,
        maximum_quote_volume_error=maximum_quote_error,
        status=status,
    )
    return normalized, audit


def normalize_futures_kline_archive(
    archive: Path,
    *,
    symbol: str,
    day: str,
    output_root: Path,
) -> tuple[Path, KlineOrderFlowAudit]:
    frame = read_archive_csv(archive, fallback_columns=_FUTURES_KLINE_COLUMNS)
    normalized, audit = normalize_futures_klines(frame, symbol=symbol, day=day)
    destination = normalized_kline_path(output_root, symbol=symbol, day=day)
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(destination, index_label='timestamp')
    return destination, audit


def normalize_metrics(
    frame: pd.DataFrame,
    *,
    symbol: str,
    day: str,
) -> tuple[pd.DataFrame, MetricsAudit]:
    """Validate and normalize one UTC day of 5m futures OI metrics."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {symbol}')
    parsed_day = _parse_day(day)
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
    missing = [column for column in required if column not in frame]
    if missing:
        raise ValueError(f'metrics is missing required columns: {", ".join(missing)}')
    working = frame.loc[:, list(required)].copy()
    timestamps = pd.to_datetime(working['create_time'], utc=True, errors='coerce')
    numeric_columns = required[2:]
    for column in numeric_columns:
        working[column] = pd.to_numeric(working[column], errors='coerce')
    finite_numeric = np.isfinite(
        working.loc[:, list(numeric_columns)].to_numpy(dtype=float)
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
    start = pd.Timestamp(parsed_day, tz='UTC')
    end = start + pd.Timedelta(days=1)
    in_day = valid_frame['timestamp'].ge(start) & valid_frame['timestamp'].lt(end)
    out_of_day_rows = int((~in_day).sum())
    day_frame = valid_frame.loc[in_day].copy()
    duplicate_timestamps = int(day_frame['timestamp'].duplicated().sum())
    day_frame = day_frame.set_index('timestamp').sort_index()
    expected_index = pd.date_range(start, end, freq='5min', inclusive='left')
    missing_timestamps = len(expected_index.difference(day_frame.index))
    normalized = day_frame.drop(columns=['create_time']).reindex(expected_index)
    status = 'PASS'
    if invalid_rows or out_of_day_rows or duplicate_timestamps or missing_timestamps:
        status = 'FAIL'
    audit = MetricsAudit(
        symbol=symbol,
        day=day,
        rows=len(frame),
        duplicate_timestamps=duplicate_timestamps,
        invalid_rows=invalid_rows,
        out_of_day_rows=out_of_day_rows,
        missing_five_minute_timestamps=missing_timestamps,
        status=status,
    )
    return normalized, audit


def normalize_metrics_archive(
    archive: Path,
    *,
    symbol: str,
    day: str,
    output_root: Path,
) -> tuple[Path, MetricsAudit]:
    frame = read_archive_csv(archive)
    normalized, audit = normalize_metrics(frame, symbol=symbol, day=day)
    destination = normalized_metrics_path(output_root, symbol=symbol, day=day)
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(destination, index_label='timestamp')
    return destination, audit


def inspect_archive_schema(path: Path) -> tuple[int, tuple[str, ...]]:
    frame = read_archive_csv(path)
    return len(frame), tuple(str(column) for column in frame.columns)


def _parse_day(value: str) -> date:
    if len(value) != 10:
        raise ValueError('day must use YYYY-MM-DD')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError('day must use YYYY-MM-DD') from None
    return parsed


def _validate_kline_spec(spec: FuturesKlineArchiveSpec) -> None:
    if spec.symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f'unsupported order-flow symbol: {spec.symbol}')
    if spec.cadence not in {'daily', 'monthly'}:
        raise ValueError(f'unsupported kline archive cadence: {spec.cadence}')
    if spec.cadence == 'daily':
        _parse_day(spec.day)
    else:
        if len(spec.day) != 7:
            raise ValueError('monthly kline period must use YYYY-MM')
        try:
            pd.Period(spec.day, freq='M')
        except ValueError:
            raise ValueError('monthly kline period must use YYYY-MM') from None
    if spec.interval != '5m':
        raise ValueError('order-flow kline interval must be 5m')


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized == 'true':
        return True
    if normalized == 'false':
        return False
    return None
