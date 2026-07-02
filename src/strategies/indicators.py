from __future__ import annotations

import numpy as np
import pandas as pd


def _validate_window(window: int | np.integer) -> int:
    if isinstance(window, bool) or not isinstance(window, (int, np.integer)) or window <= 0:
        raise ValueError('window must be a positive integer')
    return int(window)


def _validated_floats(values: pd.Series, *, name: str) -> pd.Series:
    try:
        floats = values.astype(float)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must contain only finite numbers') from None
    if not np.isfinite(floats.to_numpy()).all():
        raise ValueError(f'{name} must contain only finite numbers')
    return floats


def ema(values: pd.Series, window: int | np.integer) -> pd.Series:
    window = _validate_window(window)
    return _validated_floats(values, name='values').ewm(
        span=window,
        adjust=False,
        min_periods=window,
    ).mean()


def _wilder(values: pd.Series, window: int, *, seed_start: int) -> pd.Series:
    float_values = values.to_numpy(dtype=float, copy=False)
    result = np.full(len(values), np.nan, dtype=float)
    seed_end = seed_start + window
    if len(values) < seed_end:
        return pd.Series(result, index=values.index, dtype=float)

    seed_index = seed_end - 1
    result[seed_index] = float_values[seed_start:seed_end].mean()
    for index in range(seed_end, len(values)):
        result[index] = (
            result[index - 1] * (window - 1) + float_values[index]
        ) / window
    return pd.Series(result, index=values.index, dtype=float)


def rsi_wilder(close: pd.Series, window: int | np.integer = 14) -> pd.Series:
    window = _validate_window(window)
    delta = _validated_floats(close, name='close').diff()
    average_gain = _wilder(delta.clip(lower=0), window, seed_start=1)
    average_loss = _wilder(-delta.clip(upper=0), window, seed_start=1)
    relative_strength = average_gain / average_loss.where(average_loss != 0)
    rsi = 100 - 100 / (1 + relative_strength)
    return rsi.mask((average_loss == 0) & (average_gain > 0), 100).mask(
        (average_loss == 0) & (average_gain == 0),
        50,
    )


def atr_wilder(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int | np.integer = 14,
) -> pd.Series:
    window = _validate_window(window)
    if not high.index.equals(low.index) or not high.index.equals(close.index):
        raise ValueError('high, low, and close indexes must match')
    finite_high = _validated_floats(high, name='high')
    finite_low = _validated_floats(low, name='low')
    previous_close = _validated_floats(close, name='close').shift(1)
    true_range = pd.concat(
        [
            (finite_high - finite_low).abs(),
            (finite_high - previous_close).abs(),
            (finite_low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _wilder(true_range, window, seed_start=0)


def bollinger_bands(
    close: pd.Series,
    window: int | np.integer = 20,
    deviations: float = 2,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    window = _validate_window(window)
    if isinstance(deviations, bool) or not isinstance(
        deviations,
        (int, float, np.integer, np.floating),
    ):
        raise ValueError('deviations must be finite and non-negative')
    if not np.isfinite(deviations) or deviations < 0:
        raise ValueError('deviations must be finite and non-negative')
    finite_close = _validated_floats(close, name='close')
    middle = finite_close.rolling(window).mean()
    standard_deviation = finite_close.rolling(window).std(ddof=0)
    return (
        middle,
        middle + standard_deviation * deviations,
        middle - standard_deviation * deviations,
    )
