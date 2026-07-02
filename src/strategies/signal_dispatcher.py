from __future__ import annotations

from collections.abc import Callable

from src.strategies.signal_evaluators import evaluate_key_level, evaluate_rsi_reversal
from src.strategies.signal_models import MarketSnapshot, Signal, SignalMode

SignalEvaluator = Callable[[MarketSnapshot, SignalMode], Signal | None]


def dispatch_signal(
    snapshot: MarketSnapshot,
    mode: SignalMode,
    key_level: SignalEvaluator = evaluate_key_level,
    rsi: SignalEvaluator = evaluate_rsi_reversal,
) -> Signal | None:
    """Dispatch a snapshot to the evaluator selected by the signal mode."""
    if not isinstance(mode, SignalMode):
        raise ValueError(f'Unsupported signal mode: {mode!r}')

    if mode is SignalMode.KEY_LEVEL:
        return key_level(snapshot, mode)
    if mode is SignalMode.RSI_REVERSAL:
        return rsi(snapshot, mode)
    if mode is SignalMode.KEY_LEVEL_RSI:
        key_level_signal = key_level(snapshot, mode)
        if key_level_signal is not None:
            return key_level_signal
        return rsi(snapshot, mode)

    raise ValueError(f'Unsupported signal mode: {mode!r}')
