from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import pandas as pd

from src.strategies.indicators import atr_wilder


PIVOT_SPAN = 2
LOOKBACK_BARS = 240
ZONE_HALF_ATR_MULTIPLE = 0.20
MAX_ZONE_WIDTH_ATR = 0.50
MIN_TOUCH_GAP_BARS = 4
MAX_TOUCH_SCORE = 4
REACTION_BARS = 6
MIN_REACTION_ATR = 0.80
MIN_ZONE_SCORE = 5
SIGNAL_COOLDOWN_BARS = 4

PivotKind = Literal['HIGH', 'LOW']
SignalSide = Literal['BUY', 'SELL']
TriggerKind = Literal['REJECTION', 'FALSE_BREAK', 'BREAK_RETEST']


@dataclass(frozen=True, slots=True)
class ConfirmedPivot:
    pivot_index: int
    confirm_index: int
    price: float
    atr: float
    kind: PivotKind

    @property
    def lower(self) -> float:
        return self.price - self.atr * ZONE_HALF_ATR_MULTIPLE

    @property
    def upper(self) -> float:
        return self.price + self.atr * ZONE_HALF_ATR_MULTIPLE


def build_key_level_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    """Build closed-bar KEY_LEVEL_V2 candidates without future leakage."""
    required = {'Open', 'High', 'Low', 'Close'}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f'key level data is missing columns: {", ".join(missing)}')
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError('key level data must use a DatetimeIndex')

    prices = frame.loc[:, ['Open', 'High', 'Low', 'Close']].astype(float)
    if not np.isfinite(prices.to_numpy()).all():
        raise ValueError('key level prices must be finite')

    opens = prices['Open'].to_numpy(dtype=float)
    highs = prices['High'].to_numpy(dtype=float)
    lows = prices['Low'].to_numpy(dtype=float)
    closes = prices['Close'].to_numpy(dtype=float)
    atr = atr_wilder(prices['High'], prices['Low'], prices['Close'], 14).to_numpy(dtype=float)
    pivots_by_confirmation = _confirmed_pivots(highs, lows, atr)
    active_pivots: deque[ConfirmedPivot] = deque()
    rows: list[dict[str, object]] = []
    row_index: list[pd.Timestamp] = []
    last_signal_index: dict[SignalSide, int] = {'BUY': -SIGNAL_COOLDOWN_BARS, 'SELL': -SIGNAL_COOLDOWN_BARS}

    for bar_index in range(len(frame)):
        for pivot in pivots_by_confirmation.get(bar_index, ()):
            active_pivots.append(pivot)
        minimum_pivot_index = bar_index - LOOKBACK_BARS
        while active_pivots and active_pivots[0].pivot_index < minimum_pivot_index:
            active_pivots.popleft()
        if not np.isfinite(atr[bar_index]) or atr[bar_index] <= 0:
            continue

        best = _best_candidate(
            bar_index=bar_index,
            pivots=tuple(active_pivots),
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            atr=atr,
            last_signal_index=last_signal_index,
        )
        if best is None:
            continue
        side = best['side']
        if not isinstance(side, str) or side not in {'BUY', 'SELL'}:
            continue
        last_signal_index[side] = bar_index
        rows.append(best)
        row_index.append(pd.Timestamp(frame.index[bar_index]))

    columns = [
        'side',
        'zone_lower',
        'zone_upper',
        'touch_count',
        'reaction_atr',
        'role_flip',
        'trigger',
        'score',
    ]
    return pd.DataFrame(rows, index=pd.DatetimeIndex(row_index, name=frame.index.name), columns=columns)


def _confirmed_pivots(
    highs: np.ndarray,
    lows: np.ndarray,
    atr: np.ndarray,
) -> dict[int, list[ConfirmedPivot]]:
    result: dict[int, list[ConfirmedPivot]] = {}
    for pivot_index in range(PIVOT_SPAN, len(highs) - PIVOT_SPAN):
        if not np.isfinite(atr[pivot_index]) or atr[pivot_index] <= 0:
            continue
        confirm_index = pivot_index + PIVOT_SPAN
        left_low = lows[pivot_index - PIVOT_SPAN:pivot_index]
        right_low = lows[pivot_index + 1:pivot_index + PIVOT_SPAN + 1]
        left_high = highs[pivot_index - PIVOT_SPAN:pivot_index]
        right_high = highs[pivot_index + 1:pivot_index + PIVOT_SPAN + 1]
        if lows[pivot_index] <= left_low.min() and lows[pivot_index] < right_low.min():
            result.setdefault(confirm_index, []).append(ConfirmedPivot(
                pivot_index=pivot_index,
                confirm_index=confirm_index,
                price=float(lows[pivot_index]),
                atr=float(atr[pivot_index]),
                kind='LOW',
            ))
        if highs[pivot_index] >= left_high.max() and highs[pivot_index] > right_high.max():
            result.setdefault(confirm_index, []).append(ConfirmedPivot(
                pivot_index=pivot_index,
                confirm_index=confirm_index,
                price=float(highs[pivot_index]),
                atr=float(atr[pivot_index]),
                kind='HIGH',
            ))
    return result


def _merged_zones(pivots: tuple[ConfirmedPivot, ...]) -> list[tuple[float, float, list[ConfirmedPivot]]]:
    zones: list[tuple[float, float, list[ConfirmedPivot]]] = []
    for pivot in sorted(pivots, key=lambda item: item.lower):
        if not zones or pivot.lower > zones[-1][1]:
            zones.append((pivot.lower, pivot.upper, [pivot]))
            continue
        lower, upper, members = zones[-1]
        zones[-1] = (lower, max(upper, pivot.upper), [*members, pivot])
    return zones


def _independent_pivots(pivots: list[ConfirmedPivot], kind: PivotKind) -> list[ConfirmedPivot]:
    selected: list[ConfirmedPivot] = []
    for pivot in sorted((item for item in pivots if item.kind == kind), key=lambda item: item.pivot_index):
        if not selected or pivot.pivot_index - selected[-1].pivot_index >= MIN_TOUCH_GAP_BARS:
            selected.append(pivot)
    return selected


def _reaction_strength(
    pivot: ConfirmedPivot,
    *,
    bar_index: int,
    highs: np.ndarray,
    lows: np.ndarray,
) -> float:
    end = min(bar_index + 1, pivot.pivot_index + REACTION_BARS + 1)
    if end <= pivot.pivot_index + 1:
        return 0.0
    if pivot.kind == 'LOW':
        movement = highs[pivot.pivot_index + 1:end].max() - pivot.price
    else:
        movement = pivot.price - lows[pivot.pivot_index + 1:end].min()
    return max(0.0, float(movement / pivot.atr))


def _trigger(
    *,
    side: SignalSide,
    role_flip: bool,
    zone_lower: float,
    zone_upper: float,
    bar_index: int,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> TriggerKind | None:
    if side == 'BUY':
        touched = lows[bar_index] <= zone_upper and highs[bar_index] >= zone_lower
        if not touched or closes[bar_index] <= zone_upper:
            return None
        if lows[bar_index] < zone_lower:
            return 'FALSE_BREAK'
        if role_flip and bar_index > 0 and closes[bar_index - 1] > zone_upper:
            return 'BREAK_RETEST'
        if closes[bar_index] >= opens[bar_index]:
            return 'REJECTION'
        return None

    touched = highs[bar_index] >= zone_lower and lows[bar_index] <= zone_upper
    if not touched or closes[bar_index] >= zone_lower:
        return None
    if highs[bar_index] > zone_upper:
        return 'FALSE_BREAK'
    if role_flip and bar_index > 0 and closes[bar_index - 1] < zone_lower:
        return 'BREAK_RETEST'
    if closes[bar_index] <= opens[bar_index]:
        return 'REJECTION'
    return None


def _best_candidate(
    *,
    bar_index: int,
    pivots: tuple[ConfirmedPivot, ...],
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr: np.ndarray,
    last_signal_index: dict[SignalSide, int],
) -> dict[str, object] | None:
    candidates: list[dict[str, object]] = []
    for zone_lower, zone_upper, members in _merged_zones(pivots):
        if zone_upper - zone_lower > atr[bar_index] * MAX_ZONE_WIDTH_ATR:
            continue
        if highs[bar_index] < zone_lower or lows[bar_index] > zone_upper:
            continue
        role_flip = any(item.kind == 'LOW' for item in members) and any(item.kind == 'HIGH' for item in members)
        for side, kind in (('BUY', 'LOW'), ('SELL', 'HIGH')):
            typed_side = cast(SignalSide, side)
            typed_kind = cast(PivotKind, kind)
            if bar_index - last_signal_index[typed_side] < SIGNAL_COOLDOWN_BARS:
                continue
            touches = _independent_pivots(members, typed_kind)
            if len(touches) < 2:
                continue
            reactions = [
                _reaction_strength(pivot, bar_index=bar_index, highs=highs, lows=lows)
                for pivot in touches
            ]
            median_reaction = float(np.median(reactions))
            if median_reaction < MIN_REACTION_ATR:
                continue
            score = min(len(touches), MAX_TOUCH_SCORE) + 1 + 1 + int(role_flip)
            if score < MIN_ZONE_SCORE:
                continue
            trigger = _trigger(
                side=typed_side,
                role_flip=role_flip,
                zone_lower=zone_lower,
                zone_upper=zone_upper,
                bar_index=bar_index,
                opens=opens,
                highs=highs,
                lows=lows,
                closes=closes,
            )
            if trigger is None:
                continue
            candidates.append({
                'side': typed_side,
                'zone_lower': float(zone_lower),
                'zone_upper': float(zone_upper),
                'touch_count': len(touches),
                'reaction_atr': median_reaction,
                'role_flip': role_flip,
                'trigger': trigger,
                'score': score,
            })
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (int(item['score']), float(item['reaction_atr']), int(item['touch_count'])),
    )
