"""Read-only study of short reversals after fading active-buy pushes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src.research.event_factors import FIXED_ROUND_TRIP_COST, MINIMUM_BUCKET_SAMPLES
from src.research.order_flow_events import load_funding_year, load_order_flow_year
from src.research.order_flow_failed_push import aggregate_order_flow_to_15m


TIMEFRAME = pd.Timedelta(minutes=15)
OI_LOOKBACK_BARS = 3
EVENT_COOLDOWN_BARS = 4
TAKER_BUY_RATIO_THRESHOLD = 0.55
OI_CHANGE_THRESHOLD = 0.002
PRIMARY_HORIZON = '30m'
HORIZONS = {'30m': 2, '1h': 4}
SUMMARY_COLUMNS = (
    'horizon', 'factor', 'bucket', 'samples', 'average_gross_return',
    'average_net_return', 'win_rate_pct', 'profit_factor', 'meets_minimum_sample',
)


@dataclass(frozen=True, slots=True)
class FadingPushResearchSlice:
    """One symbol/year result for the frozen fading-push study."""

    symbol: str
    year: int
    events: int
    eligible_rows: int
    excluded_metric_rows: int
    dataset_path: Path
    summary: pd.DataFrame


def build_fading_push_events(
    fifteen_minute: pd.DataFrame,
    *,
    funding_rate: pd.Series | None = None,
) -> tuple[pd.DataFrame, int, int]:
    """Build SELL events using only information known at the 15m close."""
    events, eligible_rows, excluded_metric_rows = build_fading_push_candidates(
        fifteen_minute,
        funding_rate=funding_rate,
    )
    features = _build_features(_validated_frame(fifteen_minute), funding_rate=funding_rate)
    for horizon, bars in HORIZONS.items():
        future_close = features['close'].shift(-bars).reindex(events.index)
        gross = events['close'] / future_close - 1.0
        events[f'forward_return_{horizon}'] = gross
        events[f'forward_return_{horizon}_net'] = gross - FIXED_ROUND_TRIP_COST
    return events, eligible_rows, excluded_metric_rows


def build_fading_push_candidates(
    fifteen_minute: pd.DataFrame,
    *,
    funding_rate: pd.Series | None = None,
    taker_buy_ratio_threshold: float = TAKER_BUY_RATIO_THRESHOLD,
    oi_change_threshold: float = OI_CHANGE_THRESHOLD,
    event_cooldown_bars: int = EVENT_COOLDOWN_BARS,
) -> tuple[pd.DataFrame, int, int]:
    """Build frozen candidates without attaching any future-return labels."""
    if not 0 <= taker_buy_ratio_threshold <= 1:
        raise ValueError('taker_buy_ratio_threshold must be between 0 and 1')
    if not math.isfinite(oi_change_threshold):
        raise ValueError('oi_change_threshold must be finite')
    if event_cooldown_bars < 1:
        raise ValueError('event_cooldown_bars must be positive')
    frame = _validated_frame(fifteen_minute)
    features = _build_features(frame, funding_rate=funding_rate)
    metric_window_ok = features['metrics_available'].rolling(
        OI_LOOKBACK_BARS + 1, min_periods=OI_LOOKBACK_BARS + 1,
    ).sum().eq(OI_LOOKBACK_BARS + 1)
    enough_history = features['oi_change_45m'].notna() & features['previous_close'].notna()
    qualified = (
        metric_window_ok
        & enough_history
        & features['taker_buy_ratio'].ge(taker_buy_ratio_threshold)
        & features['oi_change_45m'].ge(oi_change_threshold)
        & features['close'].lt(features['previous_close'])
    )
    events = _apply_cooldown(
        features.loc[qualified].copy(), cooldown_bars=event_cooldown_bars,
    )
    events['side'] = 'SELL'
    events.index.name = 'timestamp'
    return events, int(qualified.sum()), int((enough_history & ~metric_window_ok).sum())


def summarize_fading_push_events(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize frozen factor buckets for the primary and diagnostic horizons."""
    required = {'taker_buy_ratio', 'oi_change_45m', 'atr_pct', 'funding_rate'}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f'events is missing required columns: {", ".join(missing)}')
    working = events.copy()
    working['overall'] = 'ALL'
    working['taker_buy_ratio_tertile'] = _tertiles(working['taker_buy_ratio'])
    working['oi_change_tertile'] = _tertiles(working['oi_change_45m'])
    working['volatility_tertile'] = _tertiles(working['atr_pct'])
    working['funding_tertile'] = _tertiles(working['funding_rate'])
    factors = (
        ('overall', 'overall'),
        ('taker_buy_ratio_tertile', 'taker_buy_ratio_tertile'),
        ('oi_change_tertile', 'oi_change_tertile'),
        ('volatility_tertile', 'volatility_tertile'),
        ('funding_tertile', 'funding_tertile'),
    )
    tables: list[pd.DataFrame] = []
    for horizon in HORIZONS:
        gross_column = f'forward_return_{horizon}'
        net_column = f'forward_return_{horizon}_net'
        for factor, column in factors:
            tables.append(_summarize_factor(
                working.dropna(subset=[gross_column, net_column]), horizon, factor,
                column, gross_column, net_column,
            ))
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=SUMMARY_COLUMNS)


def run_fading_push_research(
    *, data_root: Path, output_root: Path, years: Iterable[int] = (2024, 2025),
    symbols: Iterable[str] = ('BTCUSDT', 'ETHUSDT'),
) -> list[FadingPushResearchSlice]:
    """Materialize reproducible datasets for the frozen simplified study."""
    output_root.mkdir(parents=True, exist_ok=True)
    slices: list[FadingPushResearchSlice] = []
    for year in years:
        for symbol in symbols:
            five_minute = load_order_flow_year(data_root, symbol=symbol, year=year)
            funding = load_funding_year(data_root, symbol=symbol, year=year)
            events, eligible_rows, excluded_metric_rows = build_fading_push_events(
                aggregate_order_flow_to_15m(five_minute), funding_rate=funding,
            )
            dataset_path = output_root / f'{symbol}_15m_{year}_fading_push_reversal.csv'
            events.to_csv(dataset_path)
            slices.append(FadingPushResearchSlice(
                symbol=symbol, year=year, events=len(events), eligible_rows=eligible_rows,
                excluded_metric_rows=excluded_metric_rows, dataset_path=dataset_path,
                summary=summarize_fading_push_events(events),
            ))
    return slices


def primary_validation_passed(slices: Iterable[FadingPushResearchSlice]) -> bool:
    """Apply the frozen 2025 BTC/ETH 30m gate."""
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
        raise ValueError(f'fifteen_minute is missing required columns: {", ".join(missing)}')
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError('fifteen_minute index must be a DatetimeIndex')
    result = frame.copy()
    if result.index.tz is None:
        result.index = result.index.tz_localize('UTC')
    else:
        result.index = result.index.tz_convert('UTC')
    if result.index.has_duplicates or not result.index.is_monotonic_increasing:
        raise ValueError('fifteen_minute timestamps must be unique and sorted')
    for column in required - {'metrics_available'}:
        result[column] = pd.to_numeric(result[column], errors='coerce')
    always_required = required - {'metrics_available', 'sum_open_interest'}
    if result[list(always_required)].isna().any().any():
        raise ValueError('fifteen_minute has invalid market values')
    result['metrics_available'] = _as_boolean(result['metrics_available'])
    if result['metrics_available'].isna().any():
        raise ValueError('metrics_available has invalid values')
    if result.loc[result['metrics_available'], 'sum_open_interest'].isna().any():
        raise ValueError('available metrics rows must have open interest')
    return result


def _build_features(frame: pd.DataFrame, *, funding_rate: pd.Series | None) -> pd.DataFrame:
    features = frame.copy()
    features['taker_buy_ratio'] = features['taker_buy_volume'] / features['volume']
    features['oi_change_45m'] = features['sum_open_interest'] / features['sum_open_interest'].shift(OI_LOOKBACK_BARS) - 1.0
    features['previous_close'] = features['close'].shift(1)
    previous_close = features['previous_close']
    true_range = pd.concat((
        features['high'] - features['low'],
        (features['high'] - previous_close).abs(),
        (features['low'] - previous_close).abs(),
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


def _apply_cooldown(
    candidates: pd.DataFrame,
    *,
    cooldown_bars: int = EVENT_COOLDOWN_BARS,
) -> pd.DataFrame:
    selected: list[pd.Timestamp] = []
    last_position: int | None = None
    for timestamp in candidates.index:
        position = int(timestamp.value // TIMEFRAME.value)
        if last_position is None or position - last_position >= cooldown_bars:
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
        gross = group[gross_column].astype(float)
        net = group[net_column].astype(float)
        gains = float(net.loc[net > 0].sum())
        losses = float(-net.loc[net < 0].sum())
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
