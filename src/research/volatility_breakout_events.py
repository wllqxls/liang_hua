"""Research volatility-compression breakouts without creating trade signals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.research.event_factors import FIXED_ROUND_TRIP_COST, MINIMUM_BUCKET_SAMPLES
from src.strategies.indicators import atr_wilder, bollinger_bands


ATR_WINDOW = 14
ATR_MEAN_WINDOW = 20
COMPRESSION_THRESHOLD = 0.80
BOLLINGER_WINDOW = 20
BOLLINGER_DEVIATIONS = 2
MID_DISTANCE_THRESHOLD = 0.20
BREAKOUT_WAIT_BARS = 12
_FIVE_MINUTE = pd.Timedelta(minutes=5)
_ONE_HOUR = pd.Timedelta(hours=1)
_HORIZON_BARS = {'5m': 1, '15m': 3, '1h': 12, '4h': 48}
_SUMMARY_COLUMNS = (
    'factor',
    'bucket',
    'samples',
    'average_gross_return',
    'average_net_return',
    'win_rate_pct',
    'profit_factor',
    'meets_minimum_sample',
)


@dataclass(frozen=True, slots=True)
class VolatilityBreakoutEventStudy:
    """Accepted compression events and the one-to-one breakouts they produced."""

    compression_events: pd.DataFrame
    breakout_events: pd.DataFrame


def build_volatility_breakout_event_study(
    five_minute: pd.DataFrame,
    one_hour: pd.DataFrame,
) -> VolatilityBreakoutEventStudy:
    """Build A/B events using only information known at each candle close."""
    entry = _prepare_ohlcv(five_minute, name='five_minute')
    hour = _prepare_ohlcv(one_hour, name='one_hour')
    features = _build_features(entry, hour)
    compression_events, breakout_events = _match_breakouts(features)
    breakout_events = _add_return_labels(
        breakout_events,
        close=_closed_close(entry),
    )
    return VolatilityBreakoutEventStudy(
        compression_events=compression_events,
        breakout_events=breakout_events,
    )


def summarize_breakout_buckets(events: pd.DataFrame) -> pd.DataFrame:
    """Group one-hour A-to-B returns by predeclared breakout factors."""
    required = {
        'side',
        'compression_ratio',
        'mid_distance_ratio',
        'forward_return_1h',
        'forward_return_1h_net',
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f'events is missing required columns: {", ".join(missing)}')
    usable = events.dropna(subset=['forward_return_1h', 'forward_return_1h_net']).copy()
    if usable.empty:
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)
    usable['compression_tertile'] = _tertiles(usable['compression_ratio'])
    usable['mid_distance_tertile'] = _tertiles(usable['mid_distance_ratio'])
    summaries = [
        _summarize_factor(usable, 'direction', 'side'),
        _summarize_factor(usable, 'compression_tertile', 'compression_tertile'),
        _summarize_factor(usable, 'mid_distance_tertile', 'mid_distance_tertile'),
    ]
    return pd.concat(summaries, ignore_index=True)


def _prepare_ohlcv(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    required = ('Open', 'High', 'Low', 'Close')
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f'{name} is missing required columns: {", ".join(missing)}')
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f'{name} index must be a DatetimeIndex')
    index = frame.index
    if index.tz is None:
        index = index.tz_localize('UTC')
    else:
        index = index.tz_convert('UTC')
    if index.has_duplicates:
        raise ValueError(f'{name} index must not contain duplicate timestamps')
    result = frame.loc[:, required].copy()
    result.index = index
    result = result.sort_index()
    for column in required:
        try:
            result[column] = result[column].astype(float)
        except (TypeError, ValueError):
            raise ValueError(f'{name} {column} must contain finite numbers') from None
    if not np.isfinite(result.to_numpy(dtype=float)).all():
        raise ValueError(f'{name} values must contain finite numbers')
    if (result[['High', 'Low', 'Close']] <= 0).any().any():
        raise ValueError(f'{name} High, Low, and Close must be positive')
    if (result['High'] < result['Low']).any():
        raise ValueError(f'{name} High must be greater than or equal to Low')
    return result


def _build_features(entry: pd.DataFrame, hour: pd.DataFrame) -> pd.DataFrame:
    atr = atr_wilder(entry['High'], entry['Low'], entry['Close'], ATR_WINDOW)
    atr_mean = atr.rolling(ATR_MEAN_WINDOW, min_periods=ATR_MEAN_WINDOW).mean()
    middle, upper, lower = bollinger_bands(
        hour['Close'],
        window=BOLLINGER_WINDOW,
        deviations=BOLLINGER_DEVIATIONS,
    )
    entry_features = pd.DataFrame(
        {
            'open': entry['Open'].to_numpy(),
            'high': entry['High'].to_numpy(),
            'low': entry['Low'].to_numpy(),
            'close': entry['Close'].to_numpy(),
            'atr_5m': atr.to_numpy(),
            'atr_mean_20': atr_mean.to_numpy(),
        },
        index=entry.index + _FIVE_MINUTE,
    )
    bands = pd.DataFrame(
        {
            'bb_middle_1h': middle.to_numpy(),
            'bb_upper_1h': upper.to_numpy(),
            'bb_lower_1h': lower.to_numpy(),
        },
        index=hour.index + _ONE_HOUR,
    )
    merged = pd.merge_asof(
        entry_features.sort_index().reset_index(names='event_time'),
        bands.sort_index().reset_index(names='band_available_time'),
        left_on='event_time',
        right_on='band_available_time',
        direction='backward',
    ).set_index('event_time')
    band_width = merged['bb_upper_1h'] - merged['bb_lower_1h']
    merged['compression_ratio'] = merged['atr_5m'] / merged['atr_mean_20']
    merged['mid_distance_ratio'] = (
        (merged['close'] - merged['bb_middle_1h']).abs() / band_width.where(band_width > 0)
    )
    merged['is_compression'] = (
        (merged['compression_ratio'] < COMPRESSION_THRESHOLD)
        & (merged['mid_distance_ratio'] <= MID_DISTANCE_THRESHOLD)
    )
    return merged


def _match_breakouts(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    compression_rows: list[dict[str, object]] = []
    breakout_rows: list[dict[str, object]] = []
    converted_times: set[pd.Timestamp] = set()
    pending_position: int | None = None
    pending_time: pd.Timestamp | None = None
    pending_features: dict[str, object] | None = None

    event_times = list(features.index)
    rows = features.to_dict(orient='records')
    for position, row in enumerate(rows):
        event_time = event_times[position]
        if (
            pending_position is not None
            and pending_time is not None
            and pending_features is not None
        ):
            elapsed_bars = position - pending_position
            side = _breakout_side(row)
            if elapsed_bars <= BREAKOUT_WAIT_BARS and side is not None:
                breakout_rows.append(
                    {
                        'event_time': event_time,
                        'compression_time': pending_time,
                        'side': side,
                        'close': row['close'],
                        'bb_middle_1h': row['bb_middle_1h'],
                        'bb_upper_1h': row['bb_upper_1h'],
                        'bb_lower_1h': row['bb_lower_1h'],
                        'compression_ratio': pending_features['compression_ratio'],
                        'mid_distance_ratio': pending_features['mid_distance_ratio'],
                        'bars_since_compression': elapsed_bars,
                        'event_direction': 1.0 if side == 'BUY' else -1.0,
                    }
                )
                converted_times.add(pending_time)
                pending_position = None
                pending_time = None
                pending_features = None
                continue
            if elapsed_bars <= BREAKOUT_WAIT_BARS:
                continue
            pending_position = None
            pending_time = None
            pending_features = None

        if bool(row['is_compression']):
            compression_rows.append(
                {
                    'event_time': event_time,
                    'close': row['close'],
                    'atr_5m': row['atr_5m'],
                    'atr_mean_20': row['atr_mean_20'],
                    'compression_ratio': row['compression_ratio'],
                    'bb_middle_1h': row['bb_middle_1h'],
                    'bb_upper_1h': row['bb_upper_1h'],
                    'bb_lower_1h': row['bb_lower_1h'],
                    'mid_distance_ratio': row['mid_distance_ratio'],
                }
            )
            pending_position = position
            pending_time = event_time
            pending_features = row

    compression_events = _compression_frame(compression_rows, converted_times)
    breakout_events = _breakout_frame(breakout_rows)
    return compression_events, breakout_events


def _breakout_side(row: dict[str, object]) -> str | None:
    if pd.isna(row['bb_upper_1h']) or pd.isna(row['bb_lower_1h']):
        return None
    if row['close'] > row['open'] and row['close'] > row['bb_upper_1h']:
        return 'BUY'
    if row['close'] < row['open'] and row['close'] < row['bb_lower_1h']:
        return 'SELL'
    return None


def _compression_frame(
    rows: list[dict[str, object]],
    converted_times: set[pd.Timestamp],
) -> pd.DataFrame:
    columns = [
        'close',
        'atr_5m',
        'atr_mean_20',
        'compression_ratio',
        'bb_middle_1h',
        'bb_upper_1h',
        'bb_lower_1h',
        'mid_distance_ratio',
        'converted_to_breakout',
    ]
    if not rows:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz='UTC'))
    result = pd.DataFrame(rows).set_index('event_time')
    result['converted_to_breakout'] = result.index.isin(converted_times)
    return result.loc[:, columns]


def _breakout_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        'compression_time',
        'side',
        'close',
        'bb_middle_1h',
        'bb_upper_1h',
        'bb_lower_1h',
        'compression_ratio',
        'mid_distance_ratio',
        'bars_since_compression',
        'event_direction',
    ]
    if not rows:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz='UTC'))
    return pd.DataFrame(rows).set_index('event_time').loc[:, columns]


def _closed_close(entry: pd.DataFrame) -> pd.Series:
    close = entry['Close'].copy()
    close.index = close.index + _FIVE_MINUTE
    return close


def _add_return_labels(events: pd.DataFrame, *, close: pd.Series) -> pd.DataFrame:
    result = events.copy()
    for label, bars in _HORIZON_BARS.items():
        future_close = close.shift(-bars).reindex(result.index)
        gross = result['event_direction'] * (future_close / result['close'] - 1)
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


def _summarize_factor(events: pd.DataFrame, factor: str, column: str) -> pd.DataFrame:
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
                'profit_factor': _profit_factor(net_returns),
                'meets_minimum_sample': len(group) >= MINIMUM_BUCKET_SAMPLES,
            }
        )
    return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)


def _profit_factor(net_returns: pd.Series) -> float:
    profits = net_returns[net_returns > 0].sum()
    losses = -net_returns[net_returns < 0].sum()
    if losses == 0:
        return float('nan')
    return float(profits / losses)
