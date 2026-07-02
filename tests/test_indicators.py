import numpy as np
import pandas as pd
import pytest

from src.strategies.indicators import atr_wilder, bollinger_bands, ema, rsi_wilder


@pytest.fixture
def fixed_prices() -> tuple[pd.Series, pd.Series, pd.Series]:
    close = pd.Series(
        [100 + index for index in range(20)] + [118, 116, 119, 117, 121],
        dtype=float,
    )
    return close, close + 2, close - 2


def test_ema_uses_adjust_false_and_full_warmup(
    fixed_prices: tuple[pd.Series, pd.Series, pd.Series],
) -> None:
    close, _, _ = fixed_prices

    expected = close.ewm(span=20, adjust=False, min_periods=20).mean()

    pd.testing.assert_series_equal(ema(close, 20), expected)


def test_bollinger_bands_use_population_standard_deviation(
    fixed_prices: tuple[pd.Series, pd.Series, pd.Series],
) -> None:
    close, _, _ = fixed_prices

    middle, upper, lower = bollinger_bands(close, window=20, deviations=2)
    expected_middle = close.rolling(20).mean()
    expected_std = close.rolling(20).std(ddof=0)

    pd.testing.assert_series_equal(middle, expected_middle)
    pd.testing.assert_series_equal(upper, expected_middle + expected_std * 2)
    pd.testing.assert_series_equal(lower, expected_middle - expected_std * 2)


def test_wilder_rsi_and_atr_have_stable_seed_and_recursion(
    fixed_prices: tuple[pd.Series, pd.Series, pd.Series],
) -> None:
    close, high, low = fixed_prices

    rsi = rsi_wilder(close, 14)
    atr = atr_wilder(high, low, close, 14)

    assert rsi.iloc[-1] == pytest.approx(79.4564428889596)
    assert atr.iloc[-1] == pytest.approx(4.204446064139942)
    assert rsi.iloc[:14].isna().all()
    assert atr.iloc[:14].isna().all()


def test_short_series_remain_uninitialized() -> None:
    close = pd.Series([100.0, 101.0, 102.0], index=['a', 'b', 'c'])

    assert rsi_wilder(close, 14).isna().all()
    assert atr_wilder(close + 1, close - 1, close, 14).isna().all()
    assert ema(close, 14).isna().all()
    middle, upper, lower = bollinger_bands(close, window=14)
    assert middle.isna().all()
    assert upper.isna().all()
    assert lower.isna().all()


def test_non_finite_values_do_not_produce_infinite_indicators() -> None:
    close = pd.Series([100.0] * 15 + [np.inf, 100.0])
    high = close + 1
    low = close - 1

    outputs = [ema(close, 14), rsi_wilder(close, 14), atr_wilder(high, low, close, 14)]
    outputs.extend(bollinger_bands(close, window=14))

    for output in outputs:
        assert not np.isinf(output.to_numpy()).any()
