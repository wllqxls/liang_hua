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
                'context_1h_closed_at': frame.index + pd.Timedelta(hours=1),
            },
            index=frame.index,
        ),
        pd.Timedelta(hours=1),
    )


def _four_hour_features(frame: pd.DataFrame) -> pd.DataFrame:
    short_average = ema(frame['Close'], 10)
    long_average = ema(frame['Close'], 30)
    label = pd.Series(FilterLabel.NEUTRAL, index=frame.index, dtype=object)
    label.loc[short_average > long_average] = FilterLabel.LONG
    label.loc[short_average < long_average] = FilterLabel.SHORT
    return _closed_features(
        pd.DataFrame(
            {
                'filter_label': label,
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

    snapshots = [
        MarketSnapshot(
            closed_at=_timestamp(closed_at),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            atr=float(row.atr),
            rsi=float(row.rsi),
            bollinger_upper=float(row.bollinger_upper),
            bollinger_lower=float(row.bollinger_lower),
            previous_high_20=float(row.previous_high_20),
            previous_low_20=float(row.previous_low_20),
            environment_side=cast(
                Literal['BUY', 'SELL'] | None,
                None if pd.isna(row.environment_side) else row.environment_side,
            ),
            filter_label=(
                FilterLabel.NEUTRAL
                if pd.isna(row.filter_label)
                else FilterLabel(row.filter_label)
            ),
            context_1h_closed_at=_timestamp(row.context_1h_closed_at),
            context_4h_closed_at=_timestamp(row.context_4h_closed_at),
        )
        for closed_at, row in joined.iterrows()
    ]
    return pd.Series(snapshots, index=joined.index, dtype=object, name='snapshot')
