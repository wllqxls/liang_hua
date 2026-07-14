"""Deterministic candidate generation for approved signal-mode search."""

from __future__ import annotations

import random
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from src.strategies.signal_models import (
    ACTIVE_SIGNAL_MODES,
    DEFAULT_SIGNAL_PARAMETERS,
    MarginMode,
    SignalMode,
    SignalParameters,
)


LEVERAGE_OPTIONS = [1, 2, 3, 5, 10, 20, 50, 100, 125, 150]
STAGE_ONE_BUDGET = 120
STAGE_TWO_BUDGET = 84
VALIDATION_BUDGET = 36
SIGNAL_PARAMETER_OPTIONS = [
    DEFAULT_SIGNAL_PARAMETERS,
    SignalParameters(
        key_stop_atr_multiple=1.0,
        key_target_atr_multiple=2.0,
        rsi_buy_threshold=30,
        rsi_sell_threshold=70,
        rsi_stop_atr_multiple=0.8,
        rsi_target_atr_multiple=1.5,
    ),
    SignalParameters(
        key_stop_atr_multiple=1.2,
        key_target_atr_multiple=3.0,
        rsi_buy_threshold=35,
        rsi_sell_threshold=65,
        rsi_stop_atr_multiple=1.0,
        rsi_target_atr_multiple=2.0,
    ),
    SignalParameters(
        key_stop_atr_multiple=2.0,
        key_target_atr_multiple=5.0,
        rsi_buy_threshold=35,
        rsi_sell_threshold=65,
        rsi_stop_atr_multiple=1.0,
        rsi_target_atr_multiple=1.5,
    ),
    SignalParameters(
        key_stop_atr_multiple=0.6,
        key_target_atr_multiple=1.2,
        rsi_buy_threshold=20,
        rsi_sell_threshold=80,
        rsi_stop_atr_multiple=0.6,
        rsi_target_atr_multiple=1.5,
    ),
]


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """Only dimensions the optimizer is allowed to vary."""

    mode: SignalMode
    timeframe: str
    leverage: float
    margin_mode: MarginMode
    signal_parameters: SignalParameters = DEFAULT_SIGNAL_PARAMETERS


def available_entry_timeframes(data_dir: Path, symbol: str) -> list[str]:
    """Return entry periods whose entry, 1h, and 4h CSV files all exist."""
    safe_symbol = symbol.replace('/', '_')
    return [
        timeframe
        for timeframe in ['5m', '15m']
        if all(
            (data_dir / f'{safe_symbol}_{required}.csv').exists()
            for required in [timeframe, '1h', '4h']
        )
    ]


def build_stage_one_candidates(
    *,
    entry_timeframes: list[str],
    modes: list[SignalMode],
    margin_mode: MarginMode,
    current_leverage: float,
    seed_key: str,
    budget: int = STAGE_ONE_BUDGET,
) -> list[SearchCandidate]:
    """Cover every approved mode/timeframe stratum at the requested leverage."""
    if any(mode not in ACTIVE_SIGNAL_MODES for mode in modes):
        raise ValueError('research-only modes cannot be optimized')
    leverage = float(current_leverage)
    candidates = [
        SearchCandidate(mode, timeframe, leverage, margin_mode, signal_parameters)
        for mode in modes
        for timeframe in entry_timeframes
        for signal_parameters in SIGNAL_PARAMETER_OPTIONS
    ]
    _rng(f'{seed_key}|stage1').shuffle(candidates)
    return candidates[:budget]


def build_stage_two_candidates(
    ranked: list[SearchCandidate],
    *,
    seed_key: str,
) -> list[SearchCandidate]:
    """Explore the exact base and configured options bracketing it."""
    selected: list[SearchCandidate] = []
    seen: set[SearchCandidate] = set(ranked)
    for index, base in enumerate(ranked[:12]):
        pool = [
            SearchCandidate(
                base.mode,
                base.timeframe,
                float(leverage),
                base.margin_mode,
                base.signal_parameters,
            )
            for leverage in _bracketed(base.leverage, LEVERAGE_OPTIONS)
        ]
        _rng(f'{seed_key}|stage2|{index}|{base}').shuffle(pool)
        for candidate in pool:
            if candidate not in seen:
                selected.append(candidate)
                seen.add(candidate)
            if len(selected) >= STAGE_TWO_BUDGET:
                return selected
    return selected


def _rng(seed_key: str) -> random.Random:
    digest = sha256(seed_key.encode('utf-8')).digest()
    return random.Random(int.from_bytes(digest[:8], 'big'))


def _bracketed(value: float, options: list[int]) -> list[float]:
    lower = [option for option in options if option < value]
    upper = [option for option in options if option > value]
    bracketed: list[float] = []
    if lower:
        bracketed.append(float(lower[-1]))
    bracketed.append(float(value))
    if upper:
        bracketed.append(float(upper[0]))
    return bracketed
