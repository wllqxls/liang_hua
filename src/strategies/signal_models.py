from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import pandas as pd


class SignalMode(StrEnum):
    KEY_LEVEL = 'KEY_LEVEL'
    RSI_REVERSAL = 'RSI_REVERSAL'
    KEY_LEVEL_RSI = 'KEY_LEVEL_RSI'


class MarginMode(StrEnum):
    ISOLATED = 'ISOLATED'
    CROSS = 'CROSS'


class FilterLabel(StrEnum):
    LONG = 'FILTER_LONG'
    SHORT = 'FILTER_SHORT'
    NEUTRAL = 'FILTER_NEUTRAL'


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    closed_at: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    atr: float
    rsi: float
    bollinger_upper: float
    bollinger_lower: float
    previous_high_20: float
    previous_low_20: float
    environment_side: Literal['BUY', 'SELL'] | None
    filter_label: FilterLabel
    context_1h_closed_at: pd.Timestamp
    context_4h_closed_at: pd.Timestamp


@dataclass(frozen=True, slots=True)
class Signal:
    mode: SignalMode
    strategy: str
    side: Literal['BUY', 'SELL']
    signal_time: pd.Timestamp
    signal_close: float
    atr_snapshot: float
    stop_atr_multiple: float
    target_atr_multiple: float
    stop_distance: float
    target_distance: float
    estimated_stop_price: float
    estimated_target_price: float
    environment_side: Literal['BUY', 'SELL']
    filter_label: FilterLabel
    reason: str
    score: int
