"""Deterministic candidate generation for progressive parameter search."""

from __future__ import annotations

import random
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
from pathlib import Path
from typing import Iterable


TIMEFRAME_MINUTES = {
    '1m': 1,
    '5m': 5,
    '15m': 15,
    '30m': 30,
    '1h': 60,
    '4h': 240,
    '1d': 1440,
    '1w': 10080,
}
CONTEXT_LOOKBACK_OPTIONS = [96, 192, 288]
ENTRY_LOOKBACK_OPTIONS = [10, 20, 30, 40, 50, 60]
LEVERAGE_OPTIONS = [1, 2, 3, 5, 10, 20, 50, 100, 125, 150]
STAGE_ONE_BUDGET = 120
STAGE_TWO_BUDGET = 84
VALIDATION_BUDGET = 36


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """One strategy and risk configuration to evaluate."""

    strategy: str
    context_timeframe: str
    timeframe: str
    context_lookback: int
    entry_lookback: int
    leverage: float
    take_profit_amount: float
    stop_loss_amount: float


def available_timeframe_pairs(data_dir: Path, symbol: str) -> list[tuple[str, str]]:
    """Return context/entry pairs backed by local CSV files."""
    safe_symbol = symbol.replace('/', '_')
    available = {
        timeframe
        for timeframe in TIMEFRAME_MINUTES
        if (data_dir / f'{safe_symbol}_{timeframe}.csv').exists()
    }
    pairs = [
        (context, entry)
        for context in available
        for entry in available
        if TIMEFRAME_MINUTES[context] > TIMEFRAME_MINUTES[entry]
    ]
    return sorted(
        pairs,
        key=lambda pair: (TIMEFRAME_MINUTES[pair[0]], TIMEFRAME_MINUTES[pair[1]]),
    )


def build_stage_one_candidates(
    *,
    timeframe_pairs: list[tuple[str, str]],
    strategies: list[str],
    current_leverage: float,
    take_profit_amount: float,
    stop_loss_amount: float,
    position_amount: float,
    seed_key: str,
    budget: int = STAGE_ONE_BUDGET,
) -> list[SearchCandidate]:
    """Build a stratified deterministic sample of the structural search space."""
    leverage = float(_nearest(current_leverage, LEVERAGE_OPTIONS))
    tp_base = take_profit_amount if take_profit_amount > 0 else position_amount * 0.1
    sl_base = stop_loss_amount if stop_loss_amount > 0 else position_amount * 0.1
    risk_profiles = [
        (_bounded(tp_base, 0.1, position_amount * leverage), _bounded(sl_base, 0.1, position_amount)),
        (_bounded(tp_base * 1.5, 0.1, position_amount * leverage), _bounded(sl_base, 0.1, position_amount)),
        (_bounded(tp_base, 0.1, position_amount * leverage), _bounded(sl_base * 0.75, 0.1, position_amount)),
    ]
    groups: dict[tuple[str, str, str], list[SearchCandidate]] = {}
    for strategy, (context_timeframe, timeframe) in product(strategies, timeframe_pairs):
        key = (strategy, context_timeframe, timeframe)
        groups[key] = [
            SearchCandidate(
                strategy=strategy,
                context_timeframe=context_timeframe,
                timeframe=timeframe,
                context_lookback=context_lookback,
                entry_lookback=entry_lookback,
                leverage=leverage,
                take_profit_amount=take_profit,
                stop_loss_amount=stop_loss,
            )
            for context_lookback, entry_lookback, (take_profit, stop_loss) in product(
                CONTEXT_LOOKBACK_OPTIONS,
                ENTRY_LOOKBACK_OPTIONS,
                risk_profiles,
            )
        ]
        _rng(f'{seed_key}|stage1|{key}').shuffle(groups[key])

    selected: list[SearchCandidate] = []
    ordered_keys = sorted(groups)
    while len(selected) < budget and any(groups.values()):
        for key in ordered_keys:
            if groups[key] and len(selected) < budget:
                selected.append(groups[key].pop())
    return selected


def build_stage_two_candidates(
    ranked: list[SearchCandidate],
    *,
    seed_key: str,
    position_amount: float,
    per_candidate: int = 6,
) -> list[SearchCandidate]:
    """Create deterministic local mutations around the best stage-one candidates."""
    selected: list[SearchCandidate] = []
    seen: set[SearchCandidate] = set(ranked)
    for index, base in enumerate(ranked[:12]):
        leverage_options = LEVERAGE_OPTIONS if index < 3 else _nearby(base.leverage, LEVERAGE_OPTIONS)
        pool = [
            SearchCandidate(
                strategy=base.strategy,
                context_timeframe=base.context_timeframe,
                timeframe=base.timeframe,
                context_lookback=context_lookback,
                entry_lookback=entry_lookback,
                leverage=float(leverage),
                take_profit_amount=scaled_take_profit,
                stop_loss_amount=scaled_stop_loss,
            )
            for context_lookback, entry_lookback, leverage, tp_factor, sl_factor in product(
                _nearby(base.context_lookback, CONTEXT_LOOKBACK_OPTIONS),
                _nearby(base.entry_lookback, ENTRY_LOOKBACK_OPTIONS),
                leverage_options,
                [0.75, 1.0, 1.25],
                [0.75, 1.0, 1.25],
            )
            for scaled_take_profit in [
                _scaled_exit_amount(
                    base.take_profit_amount,
                    leverage=float(leverage),
                    base_leverage=base.leverage,
                    factor=tp_factor,
                    maximum=position_amount * leverage,
                )
            ]
            for scaled_stop_loss in [
                _scaled_exit_amount(
                    base.stop_loss_amount,
                    leverage=float(leverage),
                    base_leverage=base.leverage,
                    factor=sl_factor,
                    maximum=position_amount,
                )
            ]
            if scaled_take_profit is not None and scaled_stop_loss is not None
        ]
        pool = list(dict.fromkeys(pool))
        added = 0
        if index < 3:
            for leverage in LEVERAGE_OPTIONS:
                leverage_pool = [candidate for candidate in pool if candidate.leverage == float(leverage)]
                scaled_take_profit = _scaled_exit_amount(
                    base.take_profit_amount,
                    leverage=float(leverage),
                    base_leverage=base.leverage,
                    factor=1.0,
                    maximum=position_amount * leverage,
                )
                scaled_stop_loss = _scaled_exit_amount(
                    base.stop_loss_amount,
                    leverage=float(leverage),
                    base_leverage=base.leverage,
                    factor=1.0,
                    maximum=position_amount,
                )
                candidate = next(
                    (
                        item
                        for item in leverage_pool
                        if item not in seen
                        and scaled_take_profit is not None
                        and scaled_stop_loss is not None
                        and item.context_lookback == base.context_lookback
                        and item.entry_lookback == base.entry_lookback
                        and item.take_profit_amount == scaled_take_profit
                        and item.stop_loss_amount == scaled_stop_loss
                    ),
                    None,
                )
                _rng(f'{seed_key}|stage2|{index}|{base}|{leverage}').shuffle(leverage_pool)
                if candidate is None:
                    candidate = next((item for item in leverage_pool if item not in seen), None)
                if candidate is None:
                    continue
                selected.append(candidate)
                seen.add(candidate)
                added += 1
        else:
            _rng(f'{seed_key}|stage2|{index}|{base}').shuffle(pool)
            for candidate in pool:
                if candidate in seen:
                    continue
                selected.append(candidate)
                seen.add(candidate)
                added += 1
                if added >= per_candidate:
                    break
        if len(selected) >= STAGE_TWO_BUDGET:
            break
    return selected


def _rng(seed_key: str) -> random.Random:
    digest = sha256(seed_key.encode('utf-8')).digest()
    return random.Random(int.from_bytes(digest[:8], 'big'))


def _nearest(value: float, options: Iterable[int]) -> int:
    return min(options, key=lambda option: abs(option - value))


def _nearby(value: float, options: list[int]) -> list[int]:
    nearest = _nearest(value, options)
    index = options.index(nearest)
    return options[max(0, index - 1):min(len(options), index + 2)]


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return round(min(max(value, minimum), maximum), 4)


def _scaled_exit_amount(
    base_amount: float,
    *,
    leverage: float,
    base_leverage: float,
    factor: float,
    maximum: float,
) -> float | None:
    """Scale an exit amount without changing its implied price distance."""
    amount = round(base_amount * (leverage / max(base_leverage, 1)) * factor, 4)
    if amount <= 0 or amount > maximum:
        return None
    return amount
