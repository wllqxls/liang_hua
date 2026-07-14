"""Read-only 1h study of short reversals after fading active-buy pushes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src.research.event_factors import FIXED_ROUND_TRIP_COST, MINIMUM_BUCKET_SAMPLES
from src.research.order_flow_events import load_funding_year, load_order_flow_year


TIMEFRAME = pd.Timedelta(hours=1)
SOURCE_ROWS = 12
OI_LOOKBACK_BARS = 3
EVENT_COOLDOWN_BARS = 4
TAKER_BUY_RATIO_THRESHOLD = 0.55
OI_CHANGE_THRESHOLD = 0.002
PRIMARY_HORIZON = '4h'
HORIZONS = {'1h': 1, '4h': 4}
SUMMARY_COLUMNS = (
    'horizon', 'factor', 'bucket', 'samples', 'average_gross_return',
    'average_net_return', 'win_rate_pct', 'profit_factor', 'meets_minimum_sample',
)


@dataclass(frozen=True, slots=True)
class HourlyFadingPushResearchSlice:
    """One symbol/year frozen 1h study result."""

    symbol: str
    year: int
    events: int
    eligible_rows: int
    excluded_metric_rows: int
    dataset_path: Path
    summary: pd.DataFrame


def aggregate_order_flow_to_1h(five_minute: pd.DataFrame) -> pd.DataFrame:
    """Aggregate complete 5m order-flow bars to canonical UTC 1h bars."""
    required = {
        'open', 'high', 'low', 'close', 'volume', 'taker_buy_volume',
        'sum_open_interest', 'metrics_available',
    }
    missing = sorted(required - set(five_minute.columns))
    if missing:
        raise ValueError(f'five_minute is missing required columns: {", ".join(missing)}')
    if not isinstance(five_minute.index, pd.DatetimeIndex):
        raise ValueError('five_minute index must be a DatetimeIndex')
    source = five_minute.copy()
    if source.index.tz is None:
        source.index = source.index.tz_localize('UTC')
    else:
        source.index = source.index.tz_convert('UTC')
    if source.index.has_duplicates or not source.index.is_monotonic_increasing:
        raise ValueError('five_minute timestamps must be unique and sorted')
    source['metrics_available'] = _as_boolean(source['metrics_available'])
    if source['metrics_available'].isna().any():
        raise ValueError('metrics_available has invalid values')
    for column in required - {'metrics_available'}:
        source[column] = pd.to_numeric(source[column], errors='coerce')
    always_required = required - {'metrics_available', 'sum_open_interest'}
    if source[list(always_required)].isna().any().any():
        raise ValueError('five_minute has invalid market values')
    if source.loc[source['metrics_available'], 'sum_open_interest'].isna().any():
        raise ValueError('available metrics rows must have open interest')
    grouped = source.resample('1h', label='left', closed='left')
    result = grouped.agg(
        open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
        close=('close', 'last'), volume=('volume', 'sum'),
        taker_buy_volume=('taker_buy_volume', 'sum'),
        sum_open_interest=('sum_open_interest', 'last'),
        metrics_available=('metrics_available', 'all'), source_rows=('close', 'count'),
    )
    result['metrics_available'] = result['metrics_available'] & result['source_rows'].eq(SOURCE_ROWS)
    if not result['source_rows'].eq(SOURCE_ROWS).all():
        raise ValueError('five_minute data cannot form a complete 1h grid')
    return result.drop(columns='source_rows')


def build_hourly_fading_push_events(
    hourly: pd.DataFrame, *, funding_rate: pd.Series | None = None,
) -> tuple[pd.DataFrame, int, int]:
    """Build SELL events using exclusively information known at the 1h close."""
    frame = _validated_frame(hourly)
    features = _build_features(frame, funding_rate=funding_rate)
    metric_window_ok = features['metrics_available'].rolling(
        OI_LOOKBACK_BARS + 1, min_periods=OI_LOOKBACK_BARS + 1,
    ).sum().eq(OI_LOOKBACK_BARS + 1)
    enough_history = features['oi_change_3h'].notna() & features['previous_close'].notna()
    qualified = (
        metric_window_ok & enough_history
        & features['taker_buy_ratio'].ge(TAKER_BUY_RATIO_THRESHOLD)
        & features['oi_change_3h'].ge(OI_CHANGE_THRESHOLD)
        & features['close'].lt(features['previous_close'])
    )
    events = _apply_cooldown(features.loc[qualified].copy())
    events['side'] = 'SELL'
    for horizon, bars in HORIZONS.items():
        future_close = features['close'].shift(-bars).reindex(events.index)
        gross = events['close'] / future_close - 1.0
        events[f'forward_return_{horizon}'] = gross
        events[f'forward_return_{horizon}_net'] = gross - FIXED_ROUND_TRIP_COST
    events.index.name = 'timestamp'
    return events, int(qualified.sum()), int((enough_history & ~metric_window_ok).sum())


def summarize_hourly_fading_push_events(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize frozen 1h-event returns by predeclared factor buckets."""
    required = {'taker_buy_ratio', 'oi_change_3h', 'atr_pct', 'funding_rate'}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f'events is missing required columns: {", ".join(missing)}')
    working = events.copy()
    working['overall'] = 'ALL'
    working['taker_buy_ratio_tertile'] = _tertiles(working['taker_buy_ratio'])
    working['oi_change_tertile'] = _tertiles(working['oi_change_3h'])
    working['volatility_tertile'] = _tertiles(working['atr_pct'])
    working['funding_tertile'] = _tertiles(working['funding_rate'])
    factors = (
        ('overall', 'overall'), ('taker_buy_ratio_tertile', 'taker_buy_ratio_tertile'),
        ('oi_change_tertile', 'oi_change_tertile'),
        ('volatility_tertile', 'volatility_tertile'), ('funding_tertile', 'funding_tertile'),
    )
    tables: list[pd.DataFrame] = []
    for horizon in HORIZONS:
        gross_column, net_column = f'forward_return_{horizon}', f'forward_return_{horizon}_net'
        usable = working.dropna(subset=[gross_column, net_column])
        for factor, column in factors:
            tables.append(_summarize_factor(usable, horizon, factor, column, gross_column, net_column))
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=SUMMARY_COLUMNS)


def run_hourly_fading_push_research(
    *, data_root: Path, output_root: Path, years: Iterable[int] = (2024, 2025),
    symbols: Iterable[str] = ('BTCUSDT', 'ETHUSDT'),
) -> list[HourlyFadingPushResearchSlice]:
    """Materialize reproducible 1h event datasets for the frozen study."""
    output_root.mkdir(parents=True, exist_ok=True)
    slices: list[HourlyFadingPushResearchSlice] = []
    for year in years:
        for symbol in symbols:
            five_minute = load_order_flow_year(data_root, symbol=symbol, year=year)
            funding = load_funding_year(data_root, symbol=symbol, year=year)
            events, eligible_rows, excluded_metric_rows = build_hourly_fading_push_events(
                aggregate_order_flow_to_1h(five_minute), funding_rate=funding,
            )
            dataset_path = output_root / f'{symbol}_1h_{year}_fading_push_reversal.csv'
            events.to_csv(dataset_path)
            slices.append(HourlyFadingPushResearchSlice(
                symbol=symbol, year=year, events=len(events), eligible_rows=eligible_rows,
                excluded_metric_rows=excluded_metric_rows, dataset_path=dataset_path,
                summary=summarize_hourly_fading_push_events(events),
            ))
    return slices


def primary_validation_passed(slices: Iterable[HourlyFadingPushResearchSlice]) -> bool:
    """Apply the predeclared 2025 BTC/ETH four-hour aggregate gate."""
    target = [item for item in slices if item.year == 2025]
    if {item.symbol for item in target} != {'BTCUSDT', 'ETHUSDT'}:
        return False
    for item in target:
        primary = item.summary.loc[
            (item.summary['horizon'] == PRIMARY_HORIZON)
            & (item.summary['factor'] == 'overall') & (item.summary['bucket'] == 'ALL')
        ]
        if len(primary) != 1:
            return False
        row = primary.iloc[0]
        if not (int(row['samples']) >= MINIMUM_BUCKET_SAMPLES and float(row['average_net_return']) > 0 and float(row['profit_factor']) >= 1.15):
            return False
    return True


def _validated_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        'open', 'high', 'low', 'close', 'volume', 'taker_buy_volume',
        'sum_open_interest', 'metrics_available',
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f'hourly is missing required columns: {", ".join(missing)}')
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError('hourly index must be a DatetimeIndex')
    result = frame.copy()
    if result.index.tz is None:
        result.index = result.index.tz_localize('UTC')
    else:
        result.index = result.index.tz_convert('UTC')
    if result.index.has_duplicates or not result.index.is_monotonic_increasing:
        raise ValueError('hourly timestamps must be unique and sorted')
    for column in required - {'metrics_available'}:
        result[column] = pd.to_numeric(result[column], errors='coerce')
    always_required = required - {'metrics_available', 'sum_open_interest'}
    if result[list(always_required)].isna().any().any():
        raise ValueError('hourly has invalid market values')
    result['metrics_available'] = _as_boolean(result['metrics_available'])
    if result['metrics_available'].isna().any():
        raise ValueError('metrics_available has invalid values')
    if result.loc[result['metrics_available'], 'sum_open_interest'].isna().any():
        raise ValueError('available metrics rows must have open interest')
    return result


def _build_features(frame: pd.DataFrame, *, funding_rate: pd.Series | None) -> pd.DataFrame:
    features = frame.copy()
    features['taker_buy_ratio'] = features['taker_buy_volume'] / features['volume']
    features['oi_change_3h'] = features['sum_open_interest'] / features['sum_open_interest'].shift(OI_LOOKBACK_BARS) - 1.0
    features['previous_close'] = features['close'].shift(1)
    true_range = pd.concat((
        features['high'] - features['low'],
        (features['high'] - features['previous_close']).abs(),
        (features['low'] - features['previous_close']).abs(),
    ), axis=1).max(axis=1)
    features['atr_pct'] = true_range.rolling(14, min_periods=14).mean() / features['close']
    if funding_rate is None:
        features['funding_rate'] = math.nan
        return features
    funding = funding_rate.copy()
    if funding.index.tz is None:
        funding.index = funding.index.tz_localize('UTC')
    else:
        funding.index = funding.index.tz_convert('UTC')
    if funding.index.has_duplicates or not funding.index.is_monotonic_increasing:
        raise ValueError('funding_rate timestamps must be unique and sorted')
    features['funding_rate'] = funding.reindex(features.index, method='ffill')
    return features


def _apply_cooldown(candidates: pd.DataFrame) -> pd.DataFrame:
    selected: list[pd.Timestamp] = []
    last_position: int | None = None
    for timestamp in candidates.index:
        position = int(timestamp.value // TIMEFRAME.value)
        if last_position is None or position - last_position >= EVENT_COOLDOWN_BARS:
            selected.append(timestamp)
            last_position = position
    return candidates.loc[selected].copy()


def _tertiles(values: pd.Series) -> pd.Series:
    result = pd.Series('UNAVAILABLE', index=values.index, dtype='object')
    valid = pd.to_numeric(values, errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
    if valid.empty:
        return result
    if len(valid) == 1:
        result.loc[valid.index] = 'LOW'
        return result
    result.loc[valid.index] = pd.qcut(valid.rank(method='first'), q=min(3, len(valid)), labels=False).astype(str)
    return result.replace({'0': 'LOW', '1': 'MID', '2': 'HIGH'})


def _summarize_factor(events: pd.DataFrame, horizon: str, factor: str, bucket_column: str, gross_column: str, net_column: str) -> pd.DataFrame:
    rows: list[dict[str, float | int | str | bool]] = []
    for bucket, group in events.groupby(bucket_column, dropna=False, sort=True):
        gross, net = group[gross_column].astype(float), group[net_column].astype(float)
        gains, losses = float(net.loc[net > 0].sum()), float(-net.loc[net < 0].sum())
        profit_factor = math.inf if gains > 0 and losses == 0 else (gains / losses if losses else math.nan)
        rows.append({
            'horizon': horizon, 'factor': factor, 'bucket': str(bucket), 'samples': len(group),
            'average_gross_return': float(gross.mean()), 'average_net_return': float(net.mean()),
            'win_rate_pct': float((net > 0).mean() * 100), 'profit_factor': profit_factor,
            'meets_minimum_sample': len(group) >= MINIMUM_BUCKET_SAMPLES,
        })
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _as_boolean(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values
    return values.astype(str).str.lower().map({'true': True, 'false': False})
