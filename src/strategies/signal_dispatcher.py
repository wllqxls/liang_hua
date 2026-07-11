from __future__ import annotations

from collections.abc import Callable

from src.strategies.signal_evaluators import evaluate_key_level, evaluate_rsi_reversal
from src.strategies.signal_models import (
    DEFAULT_SIGNAL_PARAMETERS,
    MarketSnapshot,
    Signal,
    SignalMode,
    SignalParameters,
)

SignalEvaluator = Callable[..., Signal | None]


def dispatch_signal(
    snapshot: MarketSnapshot,
    mode: SignalMode,
    key_level: SignalEvaluator = evaluate_key_level,
    rsi: SignalEvaluator = evaluate_rsi_reversal,
    *,
    parameters: SignalParameters = DEFAULT_SIGNAL_PARAMETERS,
) -> Signal | None:
    """Dispatch a snapshot to the evaluator selected by the signal mode."""
    if not isinstance(mode, SignalMode):
        raise ValueError(f'Unsupported signal mode: {mode!r}')

    if mode is SignalMode.KEY_LEVEL:
        return _evaluate(key_level, snapshot, mode, parameters)
    if mode is SignalMode.RSI_REVERSAL:
        return _evaluate(rsi, snapshot, mode, parameters)
    if mode is SignalMode.KEY_LEVEL_RSI:
        key_level_signal = _evaluate(key_level, snapshot, mode, parameters)
        if key_level_signal is not None:
            return key_level_signal
        return _evaluate(rsi, snapshot, mode, parameters)

    raise ValueError(f'Unsupported signal mode: {mode!r}')


def _evaluate(
    evaluator: SignalEvaluator,
    snapshot: MarketSnapshot,
    mode: SignalMode,
    parameters: SignalParameters,
) -> Signal | None:
    if parameters == DEFAULT_SIGNAL_PARAMETERS:
        return evaluator(snapshot, mode)
    return evaluator(snapshot, mode, parameters=parameters)
