from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Literal

from src.strategies.signal_evaluators import build_signal
from src.strategies.signal_models import (
    DEFAULT_SIGNAL_PARAMETERS,
    FilterLabel,
    MarketSnapshot,
    PullbackFilterPreset,
    Signal,
    SignalMode,
    SignalParameters,
)


class PullbackState(StrEnum):
    READY = 'READY'
    WAIT_CONFIRMATION = 'WAIT_CONFIRMATION'
    RESET_REQUIRED = 'RESET_REQUIRED'


@dataclass(frozen=True, slots=True)
class _PullbackEvent:
    side: Literal['BUY', 'SELL']
    level: float
    atr: float
    confirmation_count: int = 0


class PullbackConfirmationMachine:
    """Emit one candidate signal for one confirmed key-level pullback event."""

    def __init__(
        self,
        *,
        parameters: SignalParameters = DEFAULT_SIGNAL_PARAMETERS,
    ) -> None:
        _validate_parameters(parameters)
        self._parameters = parameters
        self._state = PullbackState.READY
        self._event: _PullbackEvent | None = None

    @property
    def state(self) -> PullbackState:
        return self._state

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Advance one closed-candle state transition without reading future data."""
        if not _has_valid_inputs(snapshot):
            return None
        if self._state is PullbackState.READY:
            self._start_event(snapshot)
            return None
        if self._state is PullbackState.RESET_REQUIRED:
            self._maybe_reset(snapshot)
            return None

        event = self._event
        if event is None:
            raise RuntimeError('waiting state requires an event')
        self._event = _PullbackEvent(
            side=event.side,
            level=event.level,
            atr=event.atr,
            confirmation_count=event.confirmation_count + 1,
        )
        event = self._event
        if self._is_invalid(snapshot, event):
            self._finish_event()
            return None
        if self._is_confirmed(snapshot, event):
            if not self._allows_context(snapshot, event.side):
                self._finish_event()
                return None
            signal = build_signal(
                snapshot,
                SignalMode.PULLBACK_CONFIRMATION,
                strategy='PULLBACK_CONFIRMATION',
                side=event.side,
                stop_multiple=self._parameters.pullback_stop_atr_multiple,
                target_multiple=self._parameters.pullback_target_atr_multiple,
                reason=(
                    'Pullback confirmation above frozen support level'
                    if event.side == 'BUY'
                    else 'Pullback confirmation below frozen resistance level'
                ),
                score=1,
            )
            self._finish_event()
            return signal
        if event.confirmation_count >= self._parameters.pullback_confirmation_bars:
            self._finish_event()
        return None

    def _start_event(self, snapshot: MarketSnapshot) -> None:
        buy_breach = snapshot.low < snapshot.previous_low_20
        sell_breach = snapshot.high > snapshot.previous_high_20
        if buy_breach == sell_breach:
            return
        self._event = _PullbackEvent(
            side='BUY' if buy_breach else 'SELL',
            level=(snapshot.previous_low_20 if buy_breach else snapshot.previous_high_20),
            atr=snapshot.atr,
        )
        self._state = PullbackState.WAIT_CONFIRMATION

    def _is_invalid(self, snapshot: MarketSnapshot, event: _PullbackEvent) -> bool:
        distance = event.atr * self._parameters.pullback_invalidation_atr_multiple
        if event.side == 'BUY':
            return snapshot.low < event.level - distance
        return snapshot.high > event.level + distance

    @staticmethod
    def _is_confirmed(snapshot: MarketSnapshot, event: _PullbackEvent) -> bool:
        if event.side == 'BUY':
            return snapshot.close > event.level and snapshot.close > snapshot.open
        return snapshot.close < event.level and snapshot.close < snapshot.open

    def _allows_context(
        self,
        snapshot: MarketSnapshot,
        side: Literal['BUY', 'SELL'],
    ) -> bool:
        if self._parameters.pullback_filter_preset is PullbackFilterPreset.OFF:
            return True
        expected = FilterLabel.LONG if side == 'BUY' else FilterLabel.SHORT
        return snapshot.filter_label is expected

    def _maybe_reset(self, snapshot: MarketSnapshot) -> None:
        event = self._event
        if event is None:
            raise RuntimeError('reset state requires an event')
        distance = event.atr * self._parameters.pullback_reset_atr_multiple
        has_moved_away = (
            snapshot.high >= event.level + distance
            if event.side == 'BUY'
            else snapshot.low <= event.level - distance
        )
        if has_moved_away:
            self._event = None
            self._state = PullbackState.READY

    def _finish_event(self) -> None:
        self._state = PullbackState.RESET_REQUIRED


def _has_valid_inputs(snapshot: MarketSnapshot) -> bool:
    values = (
        snapshot.open,
        snapshot.high,
        snapshot.low,
        snapshot.close,
        snapshot.atr,
        snapshot.previous_high_20,
        snapshot.previous_low_20,
    )
    try:
        return all(isfinite(value) for value in values) and snapshot.atr > 0
    except TypeError:
        return False


def _validate_parameters(parameters: SignalParameters) -> None:
    if parameters.pullback_confirmation_bars != 3:
        raise ValueError('pullback_confirmation_bars is fixed at 3 for research')
    values = (
        parameters.pullback_stop_atr_multiple,
        parameters.pullback_target_atr_multiple,
        parameters.pullback_invalidation_atr_multiple,
        parameters.pullback_reset_atr_multiple,
    )
    if not all(isfinite(value) and value > 0 for value in values):
        raise ValueError('pullback ATR multiples must be finite positive numbers')
