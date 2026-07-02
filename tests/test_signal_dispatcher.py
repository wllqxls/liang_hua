from dataclasses import replace
from unittest.mock import MagicMock, Mock

import pandas as pd
import pytest

from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.signal_models import FilterLabel, MarketSnapshot, SignalMode


BASE = MarketSnapshot(
    opened_at=pd.Timestamp('2026-01-01 00:00', tz='UTC'),
    closed_at=pd.Timestamp('2026-01-01 00:05', tz='UTC'),
    open=100,
    high=101,
    low=99,
    close=100,
    atr=10,
    rsi=50,
    bollinger_upper=110,
    bollinger_lower=90,
    previous_high_20=105,
    previous_low_20=95,
    environment_side='BUY',
    filter_label=FilterLabel.SHORT,
    context_1h_closed_at=pd.Timestamp('2026-01-01 00:00', tz='UTC'),
    context_4h_closed_at=pd.Timestamp('2026-01-01 00:00', tz='UTC'),
)


@pytest.mark.parametrize(
    ('mode', 'selected_name'),
    [
        (SignalMode.KEY_LEVEL, 'key'),
        (SignalMode.RSI_REVERSAL, 'rsi'),
    ],
)
def test_single_mode_calls_only_selected_evaluator(
    mode: SignalMode,
    selected_name: str,
) -> None:
    snapshot = Mock(name='snapshot')
    signal = Mock(name='signal')
    key = Mock(name='key', return_value=signal)
    rsi = Mock(name='rsi', return_value=signal)

    result = dispatch_signal(snapshot, mode, key_level=key, rsi=rsi)

    assert result is signal
    selected = key if selected_name == 'key' else rsi
    unselected = rsi if selected_name == 'key' else key
    selected.assert_called_once_with(snapshot, mode)
    unselected.assert_not_called()


def test_combined_mode_returns_key_signal_without_calling_rsi() -> None:
    snapshot = Mock(name='snapshot')
    key_signal = Mock(name='key_signal')
    key = Mock(name='key', return_value=key_signal)
    rsi = Mock(name='rsi')

    result = dispatch_signal(
        snapshot,
        SignalMode.KEY_LEVEL_RSI,
        key_level=key,
        rsi=rsi,
    )

    assert result is key_signal
    key.assert_called_once_with(snapshot, SignalMode.KEY_LEVEL_RSI)
    rsi.assert_not_called()


def test_combined_mode_does_not_fallback_for_a_non_none_falsey_result() -> None:
    snapshot = Mock(name='snapshot')
    key_signal = MagicMock(name='key_signal')
    key_signal.__bool__.return_value = False
    key = Mock(name='key', return_value=key_signal)
    rsi = Mock(name='rsi')

    result = dispatch_signal(
        snapshot,
        SignalMode.KEY_LEVEL_RSI,
        key_level=key,
        rsi=rsi,
    )

    assert result is key_signal
    rsi.assert_not_called()


def test_combined_mode_falls_back_to_rsi_after_key_returns_none() -> None:
    snapshot = Mock(name='snapshot')
    rsi_signal = Mock(name='rsi_signal')
    key = Mock(name='key', return_value=None)
    rsi = Mock(name='rsi', return_value=rsi_signal)

    result = dispatch_signal(
        snapshot,
        SignalMode.KEY_LEVEL_RSI,
        key_level=key,
        rsi=rsi,
    )

    assert result is rsi_signal
    key.assert_called_once_with(snapshot, SignalMode.KEY_LEVEL_RSI)
    rsi.assert_called_once_with(snapshot, SignalMode.KEY_LEVEL_RSI)


def test_combined_mode_returns_none_when_neither_evaluator_signals() -> None:
    snapshot = Mock(name='snapshot')
    key = Mock(name='key', return_value=None)
    rsi = Mock(name='rsi', return_value=None)

    result = dispatch_signal(
        snapshot,
        SignalMode.KEY_LEVEL_RSI,
        key_level=key,
        rsi=rsi,
    )

    assert result is None
    key.assert_called_once_with(snapshot, SignalMode.KEY_LEVEL_RSI)
    rsi.assert_called_once_with(snapshot, SignalMode.KEY_LEVEL_RSI)


def test_default_key_level_binding_produces_key_level_buy_signal() -> None:
    snapshot = replace(BASE, low=94, close=96)

    signal = dispatch_signal(snapshot, SignalMode.KEY_LEVEL)

    assert signal is not None
    assert (signal.strategy, signal.side) == ('KEY_LEVEL', 'BUY')


def test_default_rsi_binding_produces_rsi_reversal_buy_signal() -> None:
    snapshot = replace(BASE, rsi=24, low=89, close=91)

    signal = dispatch_signal(snapshot, SignalMode.RSI_REVERSAL)

    assert signal is not None
    assert (signal.strategy, signal.side) == ('RSI_REVERSAL', 'BUY')


@pytest.mark.parametrize('invalid_mode', ['UNKNOWN', None, 1])
def test_invalid_mode_raises_without_calling_evaluators(invalid_mode: object) -> None:
    key = Mock(name='key')
    rsi = Mock(name='rsi')

    with pytest.raises(ValueError, match='Unsupported signal mode'):
        dispatch_signal(Mock(name='snapshot'), invalid_mode, key_level=key, rsi=rsi)  # type: ignore[arg-type]

    key.assert_not_called()
    rsi.assert_not_called()
