"""Research extreme momentum mean reversion without creating trade signals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.research.event_factors import FIXED_ROUND_TRIP_COST, MINIMUM_BUCKET_SAMPLES
from src.strategies.indicators import bollinger_bands, rsi_wilder


RSI_WINDOW = 14
RSI_UPPER_THRESHOLD = 75
RSI_LOWER_THRESHOLD = 25
BOLLINGER_WINDOW = 20
BOLLINGER_DEVIATIONS = 2
_FIVE_MINUTE = pd.Timedelta(minutes=5)
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
class MomentumReversionEventStudy:
    """First A event in each extreme episode and its next-bar B outcomes."""

    event_a: pd.DataFrame
    event_b: pd.DataFrame


def build_momentum_reversion_event_study(
    five_minute: pd.DataFrame,
) -> MomentumReversionEventStudy:
    """Build non-overlapping extreme-momentum A events and next-bar B events."""
    entry = _prepare_ohlcv(five_minute)
    features = _build_features(entry)
    event_a, event_b = _extract_events(features)
    event_a = _add_return_labels(event_a, close=_closed_close(entry))
    return MomentumReversionEventStudy(event_a=event_a, event_b=event_b)


def summarize_momentum_reversion_buckets(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize one-hour A returns by predeclared, known-at-event factors."""
    required = {
        'side',
        'rsi_extremity',
        'band_excess_ratio',
        'forward_return_1h',
        'forward_return_1h_net',
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f'events is missing required columns: {", ".join(missing)}')
    usable = events.dropna(subset=['forward_return_1h', 'forward_return_1h_net']).copy()
    if usable.empty:
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)
    usable['rsi_extremity_tertile'] = _tertiles(usable['rsi_extremity'])
    usable['band_excess_tertile'] = _tertiles(usable['band_excess_ratio'])
    summaries = [
        _summarize_factor(usable, 'direction', 'side'),
        _summarize_factor(usable, 'rsi_extremity_tertile', 'rsi_extremity_tertile'),
        _summarize_factor(usable, 'band_excess_tertile', 'band_excess_tertile'),
    ]
    return pd.concat(summaries, ignore_index=True)


def _prepare_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    required = ('Open', 'High', 'Low', 'Close')
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f'five_minute is missing required columns: {", ".join(missing)}')
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError('five_minute index must be a DatetimeIndex')
    index = frame.index
    if index.tz is None:
        index = index.tz_localize('UTC')
    else:
        index = index.tz_convert('UTC')
    if index.has_duplicates:
        raise ValueError('five_minute index must not contain duplicate timestamps')
    result = frame.loc[:, required].copy()
    result.index = index
    result = result.sort_index()
    for column in required:
        try:
            result[column] = result[column].astype(float)
        except (TypeError, ValueError):
            raise ValueError(f'five_minute {column} must contain finite numbers') from None
    if not np.isfinite(result.to_numpy(dtype=float)).all():
        raise ValueError('five_minute values must contain finite numbers')
    if (result[['High', 'Low', 'Close']] <= 0).any().any():
        raise ValueError('five_minute High, Low, and Close must be positive')
    if (result['High'] < result['Low']).any():
        raise ValueError('five_minute High must be greater than or equal to Low')
    return result


def _build_features(entry: pd.DataFrame) -> pd.DataFrame:
    rsi = rsi_wilder(entry['Close'], RSI_WINDOW)
    middle, upper, lower = bollinger_bands(
        entry['Close'],
        window=BOLLINGER_WINDOW,
        deviations=BOLLINGER_DEVIATIONS,
    )
    band_width = upper - lower
    upper_extreme = (
        (rsi > RSI_UPPER_THRESHOLD)
        & (entry['Close'] > upper)
        & (entry['Close'].shift(1) > upper.shift(1))
    )
    lower_extreme = (
        (rsi < RSI_LOWER_THRESHOLD)
        & (entry['Close'] < lower)
        & (entry['Close'].shift(1) < lower.shift(1))
    )
    side = np.select(
        [upper_extreme, lower_extreme],
        ['SELL', 'BUY'],
        default='',
    )
    rsi_extremity = np.where(
        upper_extreme,
        rsi - RSI_UPPER_THRESHOLD,
        RSI_LOWER_THRESHOLD - rsi,
    )
    band_excess = np.where(
        upper_extreme,
        (entry['Close'] - upper) / band_width.where(band_width > 0),
        (lower - entry['Close']) / band_width.where(band_width > 0),
    )
    return pd.DataFrame(
        {
            'open': entry['Open'].to_numpy(),
            'close': entry['Close'].to_numpy(),
            'rsi': rsi.to_numpy(),
            'bb_middle': middle.to_numpy(),
            'bb_upper': upper.to_numpy(),
            'bb_lower': lower.to_numpy(),
            'candidate_side': side,
            'rsi_extremity': rsi_extremity,
            'band_excess_ratio': band_excess,
        },
        index=entry.index + _FIVE_MINUTE,
    )


def _extract_events(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    event_rows: list[dict[str, object]] = []
    conversion_rows: list[dict[str, object]] = []
    active_side: str | None = None
    rows = features.to_dict(orient='records')
    event_times = list(features.index)

    for position, row in enumerate(rows):
        candidate_side = row['candidate_side']
        if not candidate_side:
            active_side = None
            continue
        if candidate_side == active_side:
            continue
        active_side = str(candidate_side)
        event_time = event_times[position]
        converted, next_time = _next_bar_conversion(rows, event_times, position, active_side)
        event_rows.append(
            {
                'event_time': event_time,
                'side': active_side,
                'close': row['close'],
                'rsi': row['rsi'],
                'bb_middle': row['bb_middle'],
                'bb_upper': row['bb_upper'],
                'bb_lower': row['bb_lower'],
                'rsi_extremity': row['rsi_extremity'],
                'band_excess_ratio': row['band_excess_ratio'],
                'event_direction': -1.0 if active_side == 'SELL' else 1.0,
                'converted_next_bar': converted,
            }
        )
        if converted and next_time is not None:
            next_row = rows[position + 1]
            conversion_rows.append(
                {
                    'event_time': next_time,
                    'source_event_time': event_time,
                    'side': active_side,
                    'close': next_row['close'],
                    'bb_middle': next_row['bb_middle'],
                }
            )
    return _event_a_frame(event_rows), _event_b_frame(conversion_rows)


def _next_bar_conversion(
    rows: list[dict[str, object]],
    event_times: list[pd.Timestamp],
    position: int,
    side: str,
) -> tuple[bool, pd.Timestamp | None]:
    next_position = position + 1
    if next_position >= len(rows):
        return False, None
    next_row = rows[next_position]
    middle = next_row['bb_middle']
    if pd.isna(middle):
        return False, None
    if side == 'SELL':
        return bool(next_row['close'] <= middle), event_times[next_position]
    return bool(next_row['close'] >= middle), event_times[next_position]


def _event_a_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        'side',
        'close',
        'rsi',
        'bb_middle',
        'bb_upper',
        'bb_lower',
        'rsi_extremity',
        'band_excess_ratio',
        'event_direction',
        'converted_next_bar',
    ]
    if not rows:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz='UTC'))
    return pd.DataFrame(rows).set_index('event_time').loc[:, columns]


def _event_b_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = ['source_event_time', 'side', 'close', 'bb_middle']
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
