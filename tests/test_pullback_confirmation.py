from __future__ import annotations

import pandas as pd

from src.strategies.pullback_confirmation import (
    PullbackConfirmationMachine,
    PullbackState,
)
from src.strategies.signal_models import (
    FilterLabel,
    MarketSnapshot,
    PullbackFilterPreset,
    SignalMode,
    SignalParameters,
)


def _snapshot(
    minute: int,
    *,
    open_price: float = 100,
    high: float = 101,
    low: float = 99,
    close: float = 100,
    previous_high: float = 105,
    previous_low: float = 95,
    filter_label: FilterLabel = FilterLabel.NEUTRAL,
) -> MarketSnapshot:
    closed_at = pd.Timestamp('2026-01-01 00:00', tz='UTC') + pd.Timedelta(
        minutes=minute
    )
    return MarketSnapshot(
        opened_at=closed_at - pd.Timedelta(minutes=5),
        closed_at=closed_at,
        open=open_price,
        high=high,
        low=low,
        close=close,
        atr=10,
        rsi=50,
        bollinger_upper=110,
        bollinger_lower=90,
        previous_high_20=previous_high,
        previous_low_20=previous_low,
        environment_side='BUY',
        filter_label=filter_label,
        context_1h_closed_at=closed_at,
        context_4h_closed_at=closed_at,
    )


def test_buy_event_waits_for_a_later_closed_confirmation_candle() -> None:
    machine = PullbackConfirmationMachine()
    event = _snapshot(5, open_price=97, high=98, low=94, close=96)
    confirmation = _snapshot(10, open_price=95, high=98, low=95, close=97)

    assert machine.evaluate(event) is None
    signal = machine.evaluate(confirmation)

    assert signal is not None
    assert signal.mode is SignalMode.PULLBACK_CONFIRMATION
    assert signal.side == 'BUY'
    assert signal.signal_time == confirmation.closed_at
    assert signal.reason == 'Pullback confirmation above frozen support level'
    assert machine.state is PullbackState.RESET_REQUIRED


def test_buy_event_is_invalidated_by_a_later_deeper_break() -> None:
    machine = PullbackConfirmationMachine()

    assert machine.evaluate(_snapshot(5, low=94, close=96)) is None
    assert machine.evaluate(_snapshot(10, low=86.9, close=90)) is None

    assert machine.state is PullbackState.RESET_REQUIRED


def test_event_expires_after_exactly_three_unconfirmed_candles() -> None:
    machine = PullbackConfirmationMachine()

    assert machine.evaluate(_snapshot(5, low=94, close=96)) is None
    assert machine.evaluate(_snapshot(10, open_price=96, close=95.5)) is None
    assert machine.evaluate(_snapshot(15, open_price=96, close=95.5)) is None
    assert machine.evaluate(_snapshot(20, open_price=96, close=95.5)) is None

    assert machine.state is PullbackState.RESET_REQUIRED


def test_completed_event_cannot_reenter_until_price_moves_away_then_new_event_occurs() -> None:
    machine = PullbackConfirmationMachine()

    assert machine.evaluate(_snapshot(5, low=94, close=96)) is None
    assert machine.evaluate(_snapshot(10, open_price=95, close=97)) is not None
    assert machine.evaluate(_snapshot(15, low=94, close=97)) is None
    assert machine.state is PullbackState.RESET_REQUIRED

    assert machine.evaluate(_snapshot(20, high=105, low=99, close=104)) is None
    assert machine.state is PullbackState.READY
    assert machine.evaluate(
        _snapshot(25, low=96, close=98, previous_low=97)
    ) is None
    signal = machine.evaluate(
        _snapshot(30, open_price=97, close=99, previous_low=97)
    )

    assert signal is not None
    assert signal.side == 'BUY'


def test_align_preset_requires_matching_4h_context_while_off_does_not() -> None:
    event = _snapshot(5, low=94, close=96, filter_label=FilterLabel.SHORT)
    confirmation = _snapshot(
        10,
        open_price=95,
        close=97,
        filter_label=FilterLabel.SHORT,
    )
    off = PullbackConfirmationMachine()
    align = PullbackConfirmationMachine(
        parameters=SignalParameters(
            pullback_filter_preset=PullbackFilterPreset.ALIGN,
        )
    )

    assert off.evaluate(event) is None
    assert off.evaluate(confirmation) is not None
    assert align.evaluate(event) is None
    assert align.evaluate(confirmation) is None
    assert align.state is PullbackState.RESET_REQUIRED


def test_sell_event_confirms_on_a_later_bearish_close_below_resistance() -> None:
    machine = PullbackConfirmationMachine()
    event = _snapshot(5, open_price=103, high=106, low=102, close=104)
    confirmation = _snapshot(10, open_price=105, high=105, low=102, close=103)

    assert machine.evaluate(event) is None
    signal = machine.evaluate(confirmation)

    assert signal is not None
    assert signal.side == 'SELL'
    assert signal.reason == 'Pullback confirmation below frozen resistance level'
