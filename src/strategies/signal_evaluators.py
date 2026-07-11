from __future__ import annotations

from math import isfinite
from typing import Literal

from src.strategies.signal_models import (
    DEFAULT_SIGNAL_PARAMETERS,
    MarketSnapshot,
    Signal,
    SignalMode,
    SignalParameters,
)


def _has_valid_inputs(snapshot: MarketSnapshot) -> bool:
    if snapshot.environment_side not in {'BUY', 'SELL'}:
        return False
    values = (
        snapshot.open,
        snapshot.high,
        snapshot.low,
        snapshot.close,
        snapshot.atr,
        snapshot.rsi,
        snapshot.bollinger_upper,
        snapshot.bollinger_lower,
        snapshot.previous_high_20,
        snapshot.previous_low_20,
    )
    try:
        return all(isfinite(value) for value in values)
    except TypeError:
        return False


def _signal(
    snapshot: MarketSnapshot,
    mode: SignalMode,
    *,
    strategy: str,
    side: Literal['BUY', 'SELL'],
    stop_multiple: float,
    target_multiple: float,
    reason: str,
    score: int,
) -> Signal:
    stop_distance = snapshot.atr * stop_multiple
    target_distance = snapshot.atr * target_multiple
    direction = 1 if side == 'BUY' else -1
    return Signal(
        mode=mode,
        strategy=strategy,
        side=side,
        signal_time=snapshot.closed_at,
        signal_close=snapshot.close,
        atr_snapshot=snapshot.atr,
        stop_atr_multiple=stop_multiple,
        target_atr_multiple=target_multiple,
        stop_distance=stop_distance,
        target_distance=target_distance,
        estimated_stop_price=snapshot.close - direction * stop_distance,
        estimated_target_price=snapshot.close + direction * target_distance,
        environment_side=side,
        filter_label=snapshot.filter_label,
        reason=reason,
        score=score,
    )


def evaluate_rsi_reversal(
    snapshot: MarketSnapshot,
    mode: SignalMode,
    *,
    parameters: SignalParameters = DEFAULT_SIGNAL_PARAMETERS,
) -> Signal | None:
    """Evaluate strict RSI/Bollinger reversal rules without using the 4h filter."""
    if not _has_valid_inputs(snapshot):
        return None
    if (
        snapshot.environment_side == 'BUY'
        and snapshot.rsi < parameters.rsi_buy_threshold
        and snapshot.low <= snapshot.bollinger_lower
        and snapshot.close > snapshot.bollinger_lower
    ):
        return _signal(
            snapshot,
            mode,
            strategy='RSI_REVERSAL',
            side='BUY',
            stop_multiple=parameters.rsi_stop_atr_multiple,
            target_multiple=parameters.rsi_target_atr_multiple,
            reason='RSI oversold with lower Bollinger Band reclaim',
            score=3,
        )
    if (
        snapshot.environment_side == 'SELL'
        and snapshot.rsi > parameters.rsi_sell_threshold
        and snapshot.high >= snapshot.bollinger_upper
        and snapshot.close < snapshot.bollinger_upper
    ):
        return _signal(
            snapshot,
            mode,
            strategy='RSI_REVERSAL',
            side='SELL',
            stop_multiple=parameters.rsi_stop_atr_multiple,
            target_multiple=parameters.rsi_target_atr_multiple,
            reason='RSI overbought with upper Bollinger Band reclaim',
            score=3,
        )
    return None


def evaluate_key_level(
    snapshot: MarketSnapshot,
    mode: SignalMode,
    *,
    parameters: SignalParameters = DEFAULT_SIGNAL_PARAMETERS,
) -> Signal | None:
    """Evaluate strict previous-key-level false-break rules."""
    if not _has_valid_inputs(snapshot):
        return None
    if (
        snapshot.environment_side == 'BUY'
        and snapshot.low < snapshot.previous_low_20
        and snapshot.close > snapshot.previous_low_20
    ):
        return _signal(
            snapshot,
            mode,
            strategy='KEY_LEVEL',
            side='BUY',
            stop_multiple=parameters.key_stop_atr_multiple,
            target_multiple=parameters.key_target_atr_multiple,
            reason='False break below the previous 20-candle low',
            score=8,
        )
    if (
        snapshot.environment_side == 'SELL'
        and snapshot.high > snapshot.previous_high_20
        and snapshot.close < snapshot.previous_high_20
    ):
        return _signal(
            snapshot,
            mode,
            strategy='KEY_LEVEL',
            side='SELL',
            stop_multiple=parameters.key_stop_atr_multiple,
            target_multiple=parameters.key_target_atr_multiple,
            reason='False break above the previous 20-candle high',
            score=8,
        )
    return None
