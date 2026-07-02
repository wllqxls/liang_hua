from __future__ import annotations

import numpy as np
import pandas as pd


def _finite_floats(values: pd.Series) -> pd.Series:
    return values.astype(float).replace([np.inf, -np.inf], np.nan)


def ema(values: pd.Series, window: int) -> pd.Series:
    return _finite_floats(values).ewm(
        span=window,
        adjust=False,
        min_periods=window,
    ).mean()


def _wilder(values: pd.Series, window: int) -> pd.Series:
    finite_values = _finite_floats(values)
    result = pd.Series(float('nan'), index=values.index, dtype=float)
    if len(values) <= window:
        return result

    result.iloc[window] = finite_values.iloc[1 : window + 1].mean()
    for index in range(window + 1, len(values)):
        result.iloc[index] = (
            result.iloc[index - 1] * (window - 1) + finite_values.iloc[index]
        ) / window
    return result


def rsi_wilder(close: pd.Series, window: int = 14) -> pd.Series:
    delta = _finite_floats(close).diff()
    average_gain = _wilder(delta.clip(lower=0), window)
    average_loss = _wilder(-delta.clip(upper=0), window)
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
    window: int = 14,
) -> pd.Series:
    finite_high = _finite_floats(high)
    finite_low = _finite_floats(low)
    previous_close = _finite_floats(close).shift(1)
    true_range = pd.concat(
        [
            (finite_high - finite_low).abs(),
            (finite_high - previous_close).abs(),
            (finite_low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _wilder(true_range, window)


def bollinger_bands(
    close: pd.Series,
    window: int = 20,
    deviations: float = 2,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    finite_close = _finite_floats(close)
    middle = finite_close.rolling(window).mean()
    standard_deviation = finite_close.rolling(window).std(ddof=0)
    return (
        middle,
        middle + standard_deviation * deviations,
        middle - standard_deviation * deviations,
    )
