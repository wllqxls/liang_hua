"""Frozen candidate adapters used only by the human-decision replay."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

import pandas as pd

from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.signal_models import (
    DEFAULT_SIGNAL_PARAMETERS,
    ManualSignalMode,
    MarketSnapshot,
    Signal,
    SignalMode,
)


HISTORICAL_BASELINE_MODES = {
    ManualSignalMode.KEY_LEVEL: SignalMode.KEY_LEVEL,
    ManualSignalMode.RSI_REVERSAL: SignalMode.RSI_REVERSAL,
    ManualSignalMode.KEY_LEVEL_RSI: SignalMode.KEY_LEVEL_RSI,
}
ORDER_FLOW_STOP_ATR_MULTIPLE = DEFAULT_SIGNAL_PARAMETERS.key_stop_atr_multiple
ORDER_FLOW_TARGET_ATR_MULTIPLE = DEFAULT_SIGNAL_PARAMETERS.key_target_atr_multiple


def validate_manual_candidate_scope(
    *,
    mode: ManualSignalMode,
    symbol: str,
    timeframe: str,
    year: int,
) -> None:
    """Reject combinations outside the frozen experimental candidate scope."""
    if mode is ManualSignalMode.ORDER_FLOW_FADING_15M:
        if symbol not in {'BTC/USDT', 'ETH/USDT'}:
            raise ValueError('主动资金退潮实验只支持 BTC/USDT 和 ETH/USDT')
        if timeframe != '15m':
            raise ValueError('主动资金退潮实验固定使用 15m 信号周期')
        if year not in {2024, 2025}:
            raise ValueError('主动资金退潮实验当前只开放 2024 和 2025 年')
    if mode is ManualSignalMode.ETH_RSI_WHITELIST_5M:
        if symbol != 'ETH/USDT' or timeframe != '5m':
            raise ValueError('ETH RSI 白名单实验固定使用 ETH/USDT 的 5m 数据')


def evaluate_manual_candidate(
    snapshot: MarketSnapshot,
    mode: ManualSignalMode,
    *,
    order_flow_features: Mapping[str, object] | None = None,
) -> Signal | None:
    """Evaluate one closed snapshot without using any future labels."""
    if mode in HISTORICAL_BASELINE_MODES:
        return dispatch_signal(snapshot, HISTORICAL_BASELINE_MODES[mode])
    if mode is ManualSignalMode.ETH_RSI_WHITELIST_5M:
        signal = dispatch_signal(snapshot, SignalMode.RSI_REVERSAL)
        if signal is None:
            return None
        return replace(
            signal,
            mode=mode,
            strategy=mode.value,
        )
    if mode is ManualSignalMode.ORDER_FLOW_FADING_15M:
        if order_flow_features is None:
            return None
        return _build_order_flow_fading_signal(snapshot, order_flow_features)
    raise ValueError(f'Unsupported manual signal mode: {mode!r}')


def _build_order_flow_fading_signal(
    snapshot: MarketSnapshot,
    features: Mapping[str, object],
) -> Signal:
    taker_buy_ratio = float(features['taker_buy_ratio'])
    oi_change = float(features['oi_change_45m'])
    funding_rate = float(features['funding_rate'])
    taker_threshold = float(features.get('taker_buy_ratio_threshold', 0.55))
    oi_threshold = float(features.get('oi_change_threshold', 0.002))
    stop_distance = snapshot.atr * ORDER_FLOW_STOP_ATR_MULTIPLE
    target_distance = snapshot.atr * ORDER_FLOW_TARGET_ATR_MULTIPLE
    funding_text = '暂无已结算值' if pd.isna(funding_rate) else f'{funding_rate * 100:.4f}%'
    reason = (
        f'主动买入占比 {taker_buy_ratio * 100:.1f}%（≥{taker_threshold * 100:g}%）'
        f'，45 分钟 OI 增长 {oi_change * 100:.2f}%（≥{oi_threshold * 100:g}%）'
        f'，但收盘低于前一根；最近资金费率 {funding_text}'
    )
    return Signal(
        mode=ManualSignalMode.ORDER_FLOW_FADING_15M,
        strategy=ManualSignalMode.ORDER_FLOW_FADING_15M.value,
        side='SELL',
        signal_time=snapshot.closed_at,
        signal_close=snapshot.close,
        atr_snapshot=snapshot.atr,
        stop_atr_multiple=ORDER_FLOW_STOP_ATR_MULTIPLE,
        target_atr_multiple=ORDER_FLOW_TARGET_ATR_MULTIPLE,
        stop_distance=stop_distance,
        target_distance=target_distance,
        estimated_stop_price=snapshot.close + stop_distance,
        estimated_target_price=snapshot.close - target_distance,
        environment_side='SELL',
        filter_label=snapshot.filter_label,
        reason=reason,
        score=4,
    )
