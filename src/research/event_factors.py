"""Build event features and post-event labels without trading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from src.strategies.market_context import build_market_snapshots
from src.strategies.indicators import atr_wilder, bollinger_bands


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
_ABSORPTION_SUMMARY_COLUMNS = (
    'factor',
    'bucket',
    'samples',
    'average_gross_return',
    'average_net_return',
    'win_rate_pct',
    'profit_factor',
    'meets_minimum_sample',
)
VOLUME_SHOCK_THRESHOLD = 1.5
RANGE_ATR_THRESHOLD = 1.0
DISPLACEMENT_ATR_THRESHOLD = 1.0
REVERSAL_ATR_THRESHOLD = 0.5
REVERSAL_WAIT_BARS = 3
TREND_CUMULATIVE_RETURN_THRESHOLD = 0.003
_TREND_HORIZONS = {
    '5m': pd.Timedelta(minutes=5),
    '15m': pd.Timedelta(minutes=15),
    '1h': pd.Timedelta(hours=1),
}
_TREND_SUMMARY_COLUMNS = (
    'horizon',
    'samples',
    'conversion_rate_pct',
    'average_gross_return',
    'average_net_return',
    'profit_factor',
)
HOURLY_BODY_THRESHOLD = 0.005
HOURLY_TWO_BAR_MOVE_THRESHOLD = 0.015
HOURLY_REVERSAL_ATR_THRESHOLD = 0.5
_HOURLY_REVERSION_HORIZONS = {
    '1h': pd.Timedelta(hours=1),
    '2h': pd.Timedelta(hours=2),
}
_HOURLY_REVERSION_SUMMARY_COLUMNS = (
    'horizon',
    'samples',
    'reversal_rate_pct',
    'average_gross_return',
    'average_net_return',
    'profit_factor',
)


@dataclass(frozen=True, slots=True)
class VolumeAbsorptionEventStudy:
    """Volume-absorption A events and their first qualifying B reversals."""

    event_a: pd.DataFrame
    event_b: pd.DataFrame


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


def build_volume_absorption_event_study(
    entry: pd.DataFrame,
    *,
    timeframe: Literal['5m', '15m'] | str,
) -> VolumeAbsorptionEventStudy:
    """Build high-volume, low-range A events and post-event B outcomes."""
    duration = _entry_duration(timeframe)
    validated = _validated_absorption_entry(entry)
    features = _absorption_features(validated, duration=duration)
    event_a, event_b = _extract_absorption_events(features)
    event_a = _add_label_columns(
        event_a,
        timeframe=timeframe,
        close=_closed_close(validated, duration),
    )
    return VolumeAbsorptionEventStudy(event_a=event_a, event_b=event_b)


def summarize_absorption_reversal_buckets(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize one-hour absorption returns using fixed factor buckets."""
    required = {
        'side',
        'volume_ratio',
        'absorption_strength',
        'forward_return_1h',
        'forward_return_1h_net',
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f'events is missing required columns: {", ".join(missing)}')
    usable = events.dropna(subset=['forward_return_1h', 'forward_return_1h_net']).copy()
    if usable.empty:
        return pd.DataFrame(columns=_ABSORPTION_SUMMARY_COLUMNS)
    usable['overall'] = 'ALL'
    usable['volume_shock_tertile'] = _tertiles(usable['volume_ratio'])
    usable['absorption_tertile'] = _tertiles(usable['absorption_strength'])
    summaries = [
        _summarize_absorption_factor(usable, 'overall', 'overall'),
        _summarize_absorption_factor(usable, 'direction', 'side'),
        _summarize_absorption_factor(
            usable,
            'volume_shock_tertile',
            'volume_shock_tertile',
        ),
        _summarize_absorption_factor(
            usable,
            'absorption_tertile',
            'absorption_tertile',
        ),
    ]
    return pd.concat(summaries, ignore_index=True)


def build_trend_inertia_event_dataset(
    entry: pd.DataFrame,
    five_minute: pd.DataFrame,
    *,
    timeframe: Literal['5m', '15m'] | str,
) -> pd.DataFrame:
    """Build first-in-streak momentum events with exact 5m-based labels."""
    duration = _entry_duration(timeframe)
    entry_close = _validated_close_frame(entry, name='entry')
    label_close = _validated_close_frame(five_minute, name='five_minute')
    features = _trend_inertia_features(entry_close, duration=duration)
    events = _extract_trend_inertia_events(features)
    return _add_trend_inertia_labels(
        events,
        five_minute_close=_closed_price(label_close, pd.Timedelta(minutes=5)),
    )


def summarize_trend_inertia_horizons(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize gross continuation and costed returns at fixed horizons."""
    rows: list[dict[str, float | int | str]] = []
    for horizon in _TREND_HORIZONS:
        gross_column = f'forward_return_{horizon}'
        net_column = f'forward_return_{horizon}_net'
        missing = [column for column in (gross_column, net_column) if column not in events]
        if missing:
            raise ValueError(f'events is missing required columns: {", ".join(missing)}')
        usable = events.dropna(subset=[gross_column, net_column])
        if usable.empty:
            continue
        gross_returns = usable[gross_column]
        net_returns = usable[net_column]
        rows.append(
            {
                'horizon': horizon,
                'samples': len(usable),
                'conversion_rate_pct': float((gross_returns > 0).mean() * 100),
                'average_gross_return': float(gross_returns.mean()),
                'average_net_return': float(net_returns.mean()),
                'profit_factor': _absorption_profit_factor(net_returns),
            }
        )
    return pd.DataFrame(rows, columns=_TREND_SUMMARY_COLUMNS)


def build_hourly_extreme_reversion_dataset(hour: pd.DataFrame) -> pd.DataFrame:
    """Build 1h extreme events and fixed one/two-hour contrarian labels."""
    validated = _validated_absorption_entry(hour)
    features = _hourly_extreme_features(validated)
    events = _extract_hourly_extreme_events(features)
    return _add_hourly_reversion_labels(
        events,
        hourly_close=_closed_price(validated['Close'], pd.Timedelta(hours=1)),
    )


def summarize_hourly_extreme_reversion(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize significant B reversals and costed contrarian returns."""
    rows: list[dict[str, float | int | str]] = []
    for horizon in _HOURLY_REVERSION_HORIZONS:
        reversal_column = f'reversed_{horizon}'
        gross_column = f'forward_return_{horizon}'
        net_column = f'forward_return_{horizon}_net'
        required = (reversal_column, gross_column, net_column)
        missing = [column for column in required if column not in events]
        if missing:
            raise ValueError(f'events is missing required columns: {", ".join(missing)}')
        usable = events.dropna(subset=[gross_column, net_column])
        if usable.empty:
            continue
        net_returns = usable[net_column]
        rows.append(
            {
                'horizon': horizon,
                'samples': len(usable),
                'reversal_rate_pct': float(usable[reversal_column].mean() * 100),
                'average_gross_return': float(usable[gross_column].mean()),
                'average_net_return': float(net_returns.mean()),
                'profit_factor': _absorption_profit_factor(net_returns),
            }
        )
    return pd.DataFrame(rows, columns=_HOURLY_REVERSION_SUMMARY_COLUMNS)


def _validated_close_frame(frame: pd.DataFrame, *, name: str) -> pd.Series:
    if 'Close' not in frame.columns:
        raise ValueError(f'{name} is missing required column: Close')
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f'{name} index must be a DatetimeIndex')
    index = frame.index
    if index.tz is None:
        index = index.tz_localize('UTC')
    else:
        index = index.tz_convert('UTC')
    if index.has_duplicates:
        raise ValueError(f'{name} index must not contain duplicate timestamps')
    try:
        close = frame['Close'].astype(float).copy()
    except (TypeError, ValueError):
        raise ValueError(f'{name} Close must contain finite positive numbers') from None
    close.index = index
    close = close.sort_index()
    if not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        raise ValueError(f'{name} Close must contain finite positive numbers')
    return close


def _trend_inertia_features(
    close: pd.Series,
    *,
    duration: pd.Timedelta,
) -> pd.DataFrame:
    one_bar_return = close.pct_change(fill_method=None)
    cumulative_return = close / close.shift(3) - 1
    three_up = (
        (one_bar_return > 0)
        & (one_bar_return.shift(1) > 0)
        & (one_bar_return.shift(2) > 0)
    )
    three_down = (
        (one_bar_return < 0)
        & (one_bar_return.shift(1) < 0)
        & (one_bar_return.shift(2) < 0)
    )
    candidate_side = np.select(
        [
            three_up & (cumulative_return >= TREND_CUMULATIVE_RETURN_THRESHOLD),
            three_down & (cumulative_return <= -TREND_CUMULATIVE_RETURN_THRESHOLD),
        ],
        ['BUY', 'SELL'],
        default='',
    )
    return pd.DataFrame(
        {
            'close': close.to_numpy(),
            'one_bar_return': one_bar_return.to_numpy(),
            'cumulative_return_3': cumulative_return.to_numpy(),
            'candidate_side': candidate_side,
        },
        index=close.index + duration,
    )


def _extract_trend_inertia_events(features: pd.DataFrame) -> pd.DataFrame:
    event_rows: list[dict[str, object]] = []
    active_return_side = ''
    event_recorded = False
    rows = features.to_dict(orient='records')
    event_times = list(features.index)
    for position, row in enumerate(rows):
        one_bar_return = float(row['one_bar_return'])
        return_side = 'BUY' if one_bar_return > 0 else 'SELL' if one_bar_return < 0 else ''
        if return_side != active_return_side:
            active_return_side = return_side
            event_recorded = False
        candidate_side = str(row['candidate_side'])
        if not candidate_side or event_recorded:
            continue
        event_recorded = True
        event_rows.append(
            {
                'event_time': event_times[position],
                'side': candidate_side,
                'close': row['close'],
                'streak_bars': 3,
                'cumulative_return_3': row['cumulative_return_3'],
                'event_direction': 1.0 if candidate_side == 'BUY' else -1.0,
            }
        )
    columns = [
        'side',
        'close',
        'streak_bars',
        'cumulative_return_3',
        'event_direction',
    ]
    if not event_rows:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz='UTC'))
    return pd.DataFrame(event_rows).set_index('event_time').loc[:, columns]


def _closed_price(close: pd.Series, duration: pd.Timedelta) -> pd.Series:
    result = close.copy()
    result.index = result.index + duration
    return result


def _add_trend_inertia_labels(
    events: pd.DataFrame,
    *,
    five_minute_close: pd.Series,
) -> pd.DataFrame:
    result = events.copy()
    for horizon, duration in _TREND_HORIZONS.items():
        target_times = result.index + duration
        future_close = pd.Series(
            five_minute_close.reindex(target_times).to_numpy(),
            index=result.index,
            dtype=float,
        )
        gross = result['event_direction'] * (future_close / result['close'] - 1)
        result[f'forward_return_{horizon}'] = gross
        result[f'forward_return_{horizon}_net'] = gross - FIXED_ROUND_TRIP_COST
    return result


def _hourly_extreme_features(hour: pd.DataFrame) -> pd.DataFrame:
    body_return = hour['Close'] / hour['Open'] - 1
    two_bar_move = hour['Close'] / hour['Open'].shift(1) - 1
    middle, upper, lower = bollinger_bands(hour['Close'], window=20, deviations=2)
    atr = atr_wilder(hour['High'], hour['Low'], hour['Close'], 14)
    two_up = (
        (body_return >= HOURLY_BODY_THRESHOLD)
        & (body_return.shift(1) >= HOURLY_BODY_THRESHOLD)
        & (two_bar_move >= HOURLY_TWO_BAR_MOVE_THRESHOLD)
    )
    two_down = (
        (body_return <= -HOURLY_BODY_THRESHOLD)
        & (body_return.shift(1) <= -HOURLY_BODY_THRESHOLD)
        & (two_bar_move <= -HOURLY_TWO_BAR_MOVE_THRESHOLD)
    )
    band_up = (
        (body_return >= HOURLY_BODY_THRESHOLD)
        & (hour['Close'] > upper)
    )
    band_down = (
        (body_return <= -HOURLY_BODY_THRESHOLD)
        & (hour['Close'] < lower)
    )
    candidate_side = np.select(
        [two_up | band_up, two_down | band_down],
        ['SELL', 'BUY'],
        default='',
    )
    trigger = np.select(
        [
            (two_up & band_up) | (two_down & band_down),
            two_up | two_down,
            band_up | band_down,
        ],
        ['BOTH', 'TWO_BAR', 'BOLLINGER'],
        default='',
    )
    return pd.DataFrame(
        {
            'close': hour['Close'].to_numpy(),
            'atr': atr.to_numpy(),
            'body_pct': body_return.abs().to_numpy(),
            'two_bar_move_pct': two_bar_move.abs().to_numpy(),
            'bb_middle': middle.to_numpy(),
            'bb_upper': upper.to_numpy(),
            'bb_lower': lower.to_numpy(),
            'candidate_side': candidate_side,
            'trigger': trigger,
        },
        index=hour.index + pd.Timedelta(hours=1),
    )


def _extract_hourly_extreme_events(features: pd.DataFrame) -> pd.DataFrame:
    event_rows: list[dict[str, object]] = []
    active_side = ''
    rows = features.to_dict(orient='records')
    event_times = list(features.index)
    for position, row in enumerate(rows):
        candidate_side = str(row['candidate_side'])
        if not candidate_side:
            active_side = ''
            continue
        if candidate_side == active_side:
            continue
        active_side = candidate_side
        event_rows.append(
            {
                'event_time': event_times[position],
                'side': candidate_side,
                'trigger': row['trigger'],
                'close': row['close'],
                'atr': row['atr'],
                'body_pct': row['body_pct'],
                'two_bar_move_pct': row['two_bar_move_pct'],
                'bb_middle': row['bb_middle'],
                'bb_upper': row['bb_upper'],
                'bb_lower': row['bb_lower'],
                'event_direction': 1.0 if candidate_side == 'BUY' else -1.0,
            }
        )
    columns = [
        'side',
        'trigger',
        'close',
        'atr',
        'body_pct',
        'two_bar_move_pct',
        'bb_middle',
        'bb_upper',
        'bb_lower',
        'event_direction',
    ]
    if not event_rows:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz='UTC'))
    return pd.DataFrame(event_rows).set_index('event_time').loc[:, columns]


def _add_hourly_reversion_labels(
    events: pd.DataFrame,
    *,
    hourly_close: pd.Series,
) -> pd.DataFrame:
    result = events.copy()
    reversal_threshold = HOURLY_REVERSAL_ATR_THRESHOLD * result['atr'] / result['close']
    reached_reversal = pd.Series(False, index=result.index, dtype=bool)
    for horizon, duration in _HOURLY_REVERSION_HORIZONS.items():
        target_times = result.index + duration
        future_close = pd.Series(
            hourly_close.reindex(target_times).to_numpy(),
            index=result.index,
            dtype=float,
        )
        gross = result['event_direction'] * (future_close / result['close'] - 1)
        result[f'forward_return_{horizon}'] = gross
        result[f'forward_return_{horizon}_net'] = gross - FIXED_ROUND_TRIP_COST
        reached_reversal = reached_reversal | (gross >= reversal_threshold)
        result[f'reversed_{horizon}'] = reached_reversal
    return result


def _validated_absorption_entry(entry: pd.DataFrame) -> pd.DataFrame:
    required = ('Open', 'High', 'Low', 'Close', 'Volume')
    missing = [column for column in required if column not in entry.columns]
    if missing:
        raise ValueError(f'entry is missing required columns: {", ".join(missing)}')
    if not isinstance(entry.index, pd.DatetimeIndex):
        raise ValueError('entry index must be a DatetimeIndex')
    index = entry.index
    if index.tz is None:
        index = index.tz_localize('UTC')
    else:
        index = index.tz_convert('UTC')
    if index.has_duplicates:
        raise ValueError('entry index must not contain duplicate timestamps')
    result = entry.loc[:, required].copy()
    result.index = index
    result = result.sort_index()
    for column in required:
        try:
            result[column] = result[column].astype(float)
        except (TypeError, ValueError):
            raise ValueError(f'entry {column} must contain finite numbers') from None
    if not np.isfinite(result.to_numpy(dtype=float)).all():
        raise ValueError('entry values must contain finite numbers')
    if (result[['High', 'Low', 'Close']] <= 0).any().any():
        raise ValueError('entry High, Low, and Close must be positive')
    if (result['Volume'] < 0).any():
        raise ValueError('entry Volume must contain finite non-negative numbers')
    if (result['High'] < result['Low']).any():
        raise ValueError('entry High must be greater than or equal to Low')
    return result


def _absorption_features(
    entry: pd.DataFrame,
    *,
    duration: pd.Timedelta,
) -> pd.DataFrame:
    close = entry['Close']
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            (entry['High'] - entry['Low']).abs(),
            (entry['High'] - previous_close).abs(),
            (entry['Low'] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = atr_wilder(entry['High'], entry['Low'], close, 14)
    volume_baseline = entry['Volume'].rolling(20, min_periods=20).mean().shift(1)
    volume_ratio = entry['Volume'] / volume_baseline.where(volume_baseline != 0)
    displacement = close - close.shift(3)
    range_atr = true_range / atr.where(atr > 0)
    displacement_atr = displacement.abs() / atr.where(atr > 0)
    candidate = (
        (volume_ratio >= VOLUME_SHOCK_THRESHOLD)
        & (range_atr <= RANGE_ATR_THRESHOLD)
        & (displacement_atr >= DISPLACEMENT_ATR_THRESHOLD)
    )
    side = np.select(
        [candidate & (displacement < 0), candidate & (displacement > 0)],
        ['BUY', 'SELL'],
        default='',
    )
    return pd.DataFrame(
        {
            'close': close.to_numpy(),
            'atr': atr.to_numpy(),
            'true_range': true_range.to_numpy(),
            'volume_ratio': volume_ratio.to_numpy(),
            'range_atr': range_atr.to_numpy(),
            'displacement_atr': displacement_atr.to_numpy(),
            'absorption_strength': (1 - range_atr).to_numpy(),
            'candidate_side': side,
        },
        index=entry.index + duration,
    )


def _extract_absorption_events(
    features: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    event_rows: list[dict[str, object]] = []
    reversal_rows: list[dict[str, object]] = []
    active_side = ''
    rows = features.to_dict(orient='records')
    event_times = list(features.index)
    for position, row in enumerate(rows):
        candidate_side = str(row['candidate_side'])
        if not candidate_side:
            active_side = ''
            continue
        if candidate_side == active_side:
            continue
        active_side = candidate_side
        converted, bars_to_b, b_position = _find_absorption_reversal(
            rows,
            position=position,
            side=candidate_side,
            event_close=float(row['close']),
            event_atr=float(row['atr']),
        )
        event_time = event_times[position]
        event_rows.append(
            {
                'event_time': event_time,
                'side': candidate_side,
                'close': row['close'],
                'atr': row['atr'],
                'true_range': row['true_range'],
                'volume_ratio': row['volume_ratio'],
                'range_atr': row['range_atr'],
                'displacement_atr': row['displacement_atr'],
                'absorption_strength': row['absorption_strength'],
                'event_direction': 1.0 if candidate_side == 'BUY' else -1.0,
                'converted_to_b': converted,
                'bars_to_b': bars_to_b,
                'b_time': event_times[b_position] if b_position is not None else pd.NaT,
            }
        )
        if b_position is not None:
            reversal_rows.append(
                {
                    'event_time': event_times[b_position],
                    'source_event_time': event_time,
                    'side': candidate_side,
                    'close': rows[b_position]['close'],
                    'bars_from_a': b_position - position,
                }
            )
    return _absorption_event_a_frame(event_rows), _absorption_event_b_frame(reversal_rows)


def _find_absorption_reversal(
    rows: list[dict[str, object]],
    *,
    position: int,
    side: str,
    event_close: float,
    event_atr: float,
) -> tuple[bool, int | None, int | None]:
    target = event_close + (REVERSAL_ATR_THRESHOLD * event_atr if side == 'BUY' else -REVERSAL_ATR_THRESHOLD * event_atr)
    final_position = min(position + REVERSAL_WAIT_BARS, len(rows) - 1)
    for candidate_position in range(position + 1, final_position + 1):
        candidate_close = float(rows[candidate_position]['close'])
        if (side == 'BUY' and candidate_close >= target) or (
            side == 'SELL' and candidate_close <= target
        ):
            bars_to_b = candidate_position - position
            return True, bars_to_b, candidate_position
    return False, None, None


def _absorption_event_a_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        'side',
        'close',
        'atr',
        'true_range',
        'volume_ratio',
        'range_atr',
        'displacement_atr',
        'absorption_strength',
        'event_direction',
        'converted_to_b',
        'bars_to_b',
        'b_time',
    ]
    if not rows:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz='UTC'))
    return pd.DataFrame(rows).set_index('event_time').loc[:, columns]


def _absorption_event_b_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = ['source_event_time', 'side', 'close', 'bars_from_a']
    if not rows:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz='UTC'))
    return pd.DataFrame(rows).set_index('event_time').loc[:, columns]


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


def _summarize_absorption_factor(
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
                'profit_factor': _absorption_profit_factor(net_returns),
                'meets_minimum_sample': len(group) >= MINIMUM_BUCKET_SAMPLES,
            }
        )
    return pd.DataFrame(rows, columns=_ABSORPTION_SUMMARY_COLUMNS)


def _absorption_profit_factor(net_returns: pd.Series) -> float:
    profits = net_returns[net_returns > 0].sum()
    losses = -net_returns[net_returns < 0].sum()
    if losses == 0:
        return float('nan')
    return float(profits / losses)
