from __future__ import annotations

from typing import Literal, cast

import numpy as np
import pandas as pd

from src.strategies.indicators import atr_wilder, bollinger_bands, ema, rsi_wilder
from src.strategies.signal_models import FilterLabel, MarketSnapshot

_PRICE_COLUMNS = ('Open', 'High', 'Low', 'Close')
_ENTRY_DURATIONS = {
    '5m': pd.Timedelta(minutes=5),
    '15m': pd.Timedelta(minutes=15),
}


def _validated_frame(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f'{name} must use a timezone-aware DatetimeIndex')
    if frame.index.has_duplicates:
        raise ValueError(f'{name} index must not contain duplicate timestamps')
    missing = [column for column in _PRICE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f'{name} is missing required columns: {", ".join(missing)}')

    result = frame.copy()
    try:
        numeric = result.loc[:, _PRICE_COLUMNS].astype(float)
    except (TypeError, ValueError):
        raise ValueError(f'{name} prices must contain only finite numbers') from None
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError(f'{name} prices must contain only finite numbers')
    result.loc[:, _PRICE_COLUMNS] = numeric
    result.index = result.index.tz_convert('UTC')
    return result.sort_index()


def _closed_features(frame: pd.DataFrame, duration: pd.Timedelta) -> pd.DataFrame:
    result = frame.copy()
    result.index = result.index + duration
    result.index.name = 'closed_at'
    return result


def _asof(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    return pd.merge_asof(
        left.sort_index(),
        right.sort_index(),
        left_index=True,
        right_index=True,
        direction='backward',
    )


def _entry_features(frame: pd.DataFrame, duration: pd.Timedelta) -> pd.DataFrame:
    _, upper, lower = bollinger_bands(frame['Close'], window=20, deviations=2)
    features = pd.DataFrame(
        {
            'open': frame['Open'],
            'high': frame['High'],
            'low': frame['Low'],
            'close': frame['Close'],
            'atr': atr_wilder(frame['High'], frame['Low'], frame['Close'], 14),
            'rsi': rsi_wilder(frame['Close'], 14),
            'bollinger_upper': upper,
            'bollinger_lower': lower,
            'previous_high_20': frame['High'].rolling(20).max().shift(1),
            'previous_low_20': frame['Low'].rolling(20).min().shift(1),
        },
        index=frame.index,
    )
    return _closed_features(features, duration)


def _hour_features(frame: pd.DataFrame) -> pd.DataFrame:
    average = ema(frame['Close'], 20)
    side = pd.Series(None, index=frame.index, dtype=object)
    side.loc[frame['Close'] > average] = 'BUY'
    side.loc[frame['Close'] < average] = 'SELL'
    return _closed_features(
        pd.DataFrame(
            {
                'environment_side': side,
                '_context_1h_ready': average.notna(),
                'context_1h_closed_at': frame.index + pd.Timedelta(hours=1),
            },
            index=frame.index,
        ),
        pd.Timedelta(hours=1),
    )


def _four_hour_features(frame: pd.DataFrame) -> pd.DataFrame:
    short_average = ema(frame['Close'], 10)
    long_average = ema(frame['Close'], 30)
    ready = short_average.notna() & long_average.notna()
    label = pd.Series(None, index=frame.index, dtype=object)
    label.loc[ready] = FilterLabel.NEUTRAL
    label.loc[short_average > long_average] = FilterLabel.LONG
    label.loc[short_average < long_average] = FilterLabel.SHORT
    return _closed_features(
        pd.DataFrame(
            {
                'filter_label': label,
                '_context_4h_ready': ready,
                'context_4h_closed_at': frame.index + pd.Timedelta(hours=4),
            },
            index=frame.index,
        ),
        pd.Timedelta(hours=4),
    )


def _timestamp(value: object) -> pd.Timestamp:
    return pd.Timestamp(value)


def build_market_snapshots(
    entry: pd.DataFrame,
    hour: pd.DataFrame,
    four_hour: pd.DataFrame,
    *,
    timeframe: Literal['5m', '15m'] | str,
) -> pd.Series:
    """Build immutable snapshots using only candles closed by each signal time."""
    if timeframe not in _ENTRY_DURATIONS:
        raise ValueError('timeframe must be 5m or 15m')
    entry = _validated_frame(entry, name='entry')
    hour = _validated_frame(hour, name='hour')
    four_hour = _validated_frame(four_hour, name='four_hour')

    joined = _asof(
        _asof(
            _entry_features(entry, _ENTRY_DURATIONS[timeframe]),
            _hour_features(hour),
        ),
        _four_hour_features(four_hour),
    )
    indicators = [
        'atr',
        'rsi',
        'bollinger_upper',
        'bollinger_lower',
        'previous_high_20',
        'previous_low_20',
    ]
    required = [
        *indicators,
        'filter_label',
        'context_1h_closed_at',
        'context_4h_closed_at',
    ]
    joined = joined.dropna(subset=required)
    joined = joined.loc[
        joined['_context_1h_ready'].eq(True)
        & joined['_context_4h_ready'].eq(True)
        & np.isfinite(joined[indicators].to_numpy(dtype=float)).all(axis=1)
    ]

    snapshot_columns = [
        'open',
        'high',
        'low',
        'close',
        'atr',
        'rsi',
        'bollinger_upper',
        'bollinger_lower',
        'previous_high_20',
        'previous_low_20',
        'environment_side',
        'filter_label',
        'context_1h_closed_at',
        'context_4h_closed_at',
    ]
    snapshots = []
    for values in joined.loc[:, snapshot_columns].itertuples(index=True, name=None):
        (
            closed_at,
            open_price,
            high,
            low,
            close,
            atr,
            rsi,
            bollinger_upper,
            bollinger_lower,
            previous_high_20,
            previous_low_20,
            environment_side,
            filter_label,
            context_1h_closed_at,
            context_4h_closed_at,
        ) = values
        snapshots.append(
            MarketSnapshot(
                closed_at=_timestamp(closed_at),
                open=float(open_price),
                high=float(high),
                low=float(low),
                close=float(close),
                atr=float(atr),
                rsi=float(rsi),
                bollinger_upper=float(bollinger_upper),
                bollinger_lower=float(bollinger_lower),
                previous_high_20=float(previous_high_20),
                previous_low_20=float(previous_low_20),
                environment_side=cast(
                    Literal['BUY', 'SELL'] | None,
                    None if pd.isna(environment_side) else environment_side,
                ),
                filter_label=FilterLabel(filter_label),
                context_1h_closed_at=_timestamp(context_1h_closed_at),
                context_4h_closed_at=_timestamp(context_4h_closed_at),
            )
        )
    return pd.Series(snapshots, index=joined.index, dtype=object, name='snapshot')
