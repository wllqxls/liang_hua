from unittest.mock import Mock

import pytest

from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.signal_models import SignalMode


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


@pytest.mark.parametrize('invalid_mode', ['UNKNOWN', None, 1])
def test_invalid_mode_raises_without_calling_evaluators(invalid_mode: object) -> None:
    key = Mock(name='key')
    rsi = Mock(name='rsi')

    with pytest.raises(ValueError, match='Unsupported signal mode'):
        dispatch_signal(Mock(name='snapshot'), invalid_mode, key_level=key, rsi=rsi)  # type: ignore[arg-type]

    key.assert_not_called()
    rsi.assert_not_called()
