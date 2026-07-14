"""Build key-level event features and post-event labels without trading."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from src.strategies.market_context import build_market_snapshots


FIXED_ROUND_TRIP_COST = 2 * (0.0005 + 0.0002)
MINIMUM_BUCKET_SAMPLES = 200
_TIMEFRAME_MINUTES = {'5m': 5, '15m': 15}
_HORIZON_BARS = {
    '5m': {'5m': 1, '15m': 3, '1h': 12, '4h': 48},
    '15m': {'15m': 1, '1h': 4, '4h': 16},
}
_SUMMARY_COLUMNS = (
    'factor',
    'bucket',
    'samples',
    'average_gross_return',
    'average_net_return',
    'win_rate_pct',
    'meets_minimum_sample',
)


def build_key_level_event_dataset(
    entry: pd.DataFrame,
    hour: pd.DataFrame,
    four_hour: pd.DataFrame,
    *,
    timeframe: Literal['5m', '15m'] | str,
) -> pd.DataFrame:
    """Return event-time features plus explicitly post-event return labels."""
    duration = _entry_duration(timeframe)
    volume_ratio = _volume_ratio(entry, duration=duration)
    snapshots = build_market_snapshots(
        entry,
        hour,
        four_hour,
        timeframe=timeframe,
    )
    features = _snapshot_frame(snapshots)
    if features.empty:
        return features
    features = features.join(volume_ratio, how='left')
    buy_event = features['low'] < features['previous_low_20']
    sell_event = features['high'] > features['previous_high_20']
    events = features.loc[buy_event ^ sell_event].copy()
    if events.empty:
        return _add_label_columns(events, timeframe=timeframe, close=_closed_close(entry, duration))

    events['side'] = np.where(buy_event.loc[events.index], 'BUY', 'SELL')
    event_direction = np.where(events['side'].eq('BUY'), 1.0, -1.0)
    events['breach_atr'] = np.where(
        events['side'].eq('BUY'),
        (events['previous_low_20'] - events['low']) / events['atr'],
        (events['high'] - events['previous_high_20']) / events['atr'],
    )
    events['body_atr'] = (events['close'] - events['open']).abs() / events['atr']
    events['atr_pct'] = events['atr'] / events['close']
    events['event_direction'] = event_direction
    return _add_label_columns(
        events,
        timeframe=timeframe,
        close=_closed_close(entry, duration),
    )


def summarize_one_hour_factor_buckets(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize the one-hour label by the fixed, known-at-event factors."""
    required = {
        'side',
        'filter_4h',
        'volume_ratio',
        'atr_pct',
        'forward_return_1h',
        'forward_return_1h_net',
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f'events is missing required columns: {", ".join(missing)}')
    usable = events.dropna(subset=['forward_return_1h', 'forward_return_1h_net']).copy()
    if usable.empty:
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)
    usable['volume_tertile'] = _tertiles(usable['volume_ratio'])
    usable['volatility_tertile'] = _tertiles(usable['atr_pct'])

    summaries = [
        _summarize_factor(usable, 'direction', 'side'),
        _summarize_factor(usable, 'filter_4h', 'filter_4h'),
        _summarize_factor(usable, 'volume_tertile', 'volume_tertile'),
        _summarize_factor(usable, 'volatility_tertile', 'volatility_tertile'),
    ]
    return pd.concat(summaries, ignore_index=True)


def _entry_duration(timeframe: Literal['5m', '15m'] | str) -> pd.Timedelta:
    try:
        return pd.Timedelta(minutes=_TIMEFRAME_MINUTES[timeframe])
    except KeyError as exc:
        raise ValueError('timeframe must be 5m or 15m') from exc


def _volume_ratio(entry: pd.DataFrame, *, duration: pd.Timedelta) -> pd.Series:
    if 'Volume' not in entry.columns:
        raise ValueError('entry is missing required column: Volume')
    try:
        volume = entry['Volume'].astype(float)
    except (TypeError, ValueError):
        raise ValueError('entry Volume must contain finite non-negative numbers') from None
    if not np.isfinite(volume.to_numpy()).all() or (volume < 0).any():
        raise ValueError('entry Volume must contain finite non-negative numbers')
    baseline = volume.rolling(20, min_periods=20).mean().shift(1)
    ratio = volume / baseline.where(baseline != 0)
    ratio.index = ratio.index + duration
    ratio.name = 'volume_ratio'
    return ratio


def _closed_close(entry: pd.DataFrame, duration: pd.Timedelta) -> pd.Series:
    close = entry['Close'].astype(float).copy()
    close.index = close.index + duration
    return close


def _snapshot_frame(snapshots: pd.Series) -> pd.DataFrame:
    rows = [
        {
            'open': snapshot.open,
            'high': snapshot.high,
            'low': snapshot.low,
            'close': snapshot.close,
            'atr': snapshot.atr,
            'rsi': snapshot.rsi,
            'previous_high_20': snapshot.previous_high_20,
            'previous_low_20': snapshot.previous_low_20,
            'environment_1h': snapshot.environment_side or 'NEUTRAL',
            'filter_4h': snapshot.filter_label.value,
        }
        for snapshot in snapshots
    ]
    return pd.DataFrame(rows, index=snapshots.index)


def _add_label_columns(
    events: pd.DataFrame,
    *,
    timeframe: Literal['5m', '15m'] | str,
    close: pd.Series,
) -> pd.DataFrame:
    result = events.copy()
    directions = result.get('event_direction')
    if directions is None:
        directions = pd.Series(dtype=float, index=result.index)
    for label, bars in _HORIZON_BARS[timeframe].items():
        future_close = close.shift(-bars).reindex(result.index)
        gross = directions * (future_close / result['close'] - 1)
        result[f'forward_return_{label}'] = gross
        result[f'forward_return_{label}_net'] = gross - FIXED_ROUND_TRIP_COST
    return result


def _tertiles(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors='coerce')
    if numeric.isna().any():
        raise ValueError('factor bucket values must be finite numbers')
    if len(numeric) < 3:
        return pd.Series('UNAVAILABLE', index=values.index, dtype=object)
    ranks = numeric.rank(method='first', pct=True)
    return pd.Series(
        np.select(
            [ranks <= 1 / 3, ranks <= 2 / 3],
            ['LOW', 'MID'],
            default='HIGH',
        ),
        index=values.index,
        dtype=object,
    )


def _summarize_factor(
    events: pd.DataFrame,
    factor: str,
    column: str,
) -> pd.DataFrame:
    rows: list[dict[str, float | int | str | bool]] = []
    for bucket, group in events.groupby(column, dropna=False):
        net_returns = group['forward_return_1h_net']
        rows.append(
            {
                'factor': factor,
                'bucket': str(bucket),
                'samples': len(group),
                'average_gross_return': group['forward_return_1h'].mean(),
                'average_net_return': net_returns.mean(),
                'win_rate_pct': (net_returns > 0).mean() * 100,
                'meets_minimum_sample': len(group) >= MINIMUM_BUCKET_SAMPLES,
            }
        )
    return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)
