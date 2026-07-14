from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import pandas as pd


class SignalMode(StrEnum):
    KEY_LEVEL = 'KEY_LEVEL'
    RSI_REVERSAL = 'RSI_REVERSAL'
    KEY_LEVEL_RSI = 'KEY_LEVEL_RSI'
    PULLBACK_CONFIRMATION = 'PULLBACK_CONFIRMATION'


class ActiveSignalMode(StrEnum):
    KEY_LEVEL = 'KEY_LEVEL'
    RSI_REVERSAL = 'RSI_REVERSAL'
    KEY_LEVEL_RSI = 'KEY_LEVEL_RSI'


ACTIVE_SIGNAL_MODES = (
    SignalMode.KEY_LEVEL,
    SignalMode.RSI_REVERSAL,
    SignalMode.KEY_LEVEL_RSI,
)


class PullbackFilterPreset(StrEnum):
    OFF = 'OFF'
    ALIGN = 'ALIGN'


class MarginMode(StrEnum):
    ISOLATED = 'ISOLATED'
    CROSS = 'CROSS'


class FilterLabel(StrEnum):
    LONG = 'FILTER_LONG'
    SHORT = 'FILTER_SHORT'
    NEUTRAL = 'FILTER_NEUTRAL'


@dataclass(frozen=True, slots=True)
class SignalParameters:
    key_stop_atr_multiple: float = 0.8
    key_target_atr_multiple: float = 1.5
    rsi_buy_threshold: float = 25.0
    rsi_sell_threshold: float = 75.0
    rsi_stop_atr_multiple: float = 0.6
    rsi_target_atr_multiple: float = 1.2
    pullback_stop_atr_multiple: float = 0.8
    pullback_target_atr_multiple: float = 1.5
    pullback_confirmation_bars: int = 3
    pullback_invalidation_atr_multiple: float = 0.8
    pullback_reset_atr_multiple: float = 1.0
    pullback_filter_preset: PullbackFilterPreset = PullbackFilterPreset.OFF


DEFAULT_SIGNAL_PARAMETERS = SignalParameters()


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    opened_at: pd.Timestamp
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


@dataclass(frozen=True, slots=True)
class TradePlan:
    signal: Signal
    fill_time: pd.Timestamp
    fill_price: float
    atr_snapshot: float
    quantity: float
    opening_amount: float
    notional_amount: float
    leverage: float
    margin_mode: MarginMode
    stop_price: float
    target_price: float
    expected_stop_amount: float
    expected_target_amount: float
    liquidation_price: float


@dataclass(frozen=True, slots=True)
class SimulationTrade:
    signal: Signal
    fill_time: pd.Timestamp
    fill_price: float
    atr_snapshot: float
    quantity: float
    opening_amount: float
    notional_amount: float
    leverage: float
    margin_mode: MarginMode
    stop_price: float
    target_price: float
    expected_stop_amount: float
    expected_target_amount: float
    liquidation_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: Literal['STOP', 'TARGET', 'LIQUIDATION', 'FINALIZE']
    entry_commission: float
    exit_commission: float
    funding: float
    pnl: float
    pnl_percent: float
    environment_side: Literal['BUY', 'SELL']
    filter_label: FilterLabel

    @property
    def signal_time(self) -> pd.Timestamp:
        return self.signal.signal_time

    @property
    def signal_close(self) -> float:
        return self.signal.signal_close

    @property
    def side(self) -> Literal['BUY', 'SELL']:
        return self.signal.side

    @property
    def mode(self) -> SignalMode:
        return self.signal.mode

    @property
    def strategy(self) -> str:
        return self.signal.strategy


@dataclass(frozen=True, slots=True)
class SimulationResult:
    trades: tuple[SimulationTrade, ...]
    equity_curve: pd.Series
    maximum_concurrent_positions: int
