"""Frozen candidate adapters used only by the human-decision replay."""

from __future__ import annotations

from dataclasses import replace
from math import isfinite
from typing import Mapping

import pandas as pd

from src.strategies.key_level_v2 import MIN_REWARD_RISK, MIN_ZONE_SCORE
from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.signal_models import (
    DEFAULT_SIGNAL_PARAMETERS,
    ManualSignalMode,
    MarketSnapshot,
    Signal,
    SignalMode,
    StructuralRisk,
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
    if mode is ManualSignalMode.ORDER_FLOW_ABSORPTION_15M:
        if symbol not in {'BTC/USDT', 'ETH/USDT'}:
            raise ValueError('相对吸收实验只支持 BTC/USDT 和 ETH/USDT')
        if timeframe != '15m':
            raise ValueError('相对吸收实验固定使用 15m 信号周期')
        if year not in {2023, 2024, 2025}:
            raise ValueError('相对吸收实验只开放 2023、2024 和 2025 年')
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
    if mode is ManualSignalMode.KEY_LEVEL_V2:
        if order_flow_features is None:
            return None
        return _build_key_level_v2_signal(snapshot, order_flow_features)
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
    if mode is ManualSignalMode.ORDER_FLOW_ABSORPTION_15M:
        if order_flow_features is None:
            return None
        return _build_order_flow_absorption_signal(snapshot, order_flow_features)
    raise ValueError(f'Unsupported manual signal mode: {mode!r}')


def _build_key_level_v2_signal(
    snapshot: MarketSnapshot,
    features: Mapping[str, object],
) -> Signal:
    side = str(features['side'])
    if side not in {'BUY', 'SELL'}:
        raise ValueError('KEY_LEVEL_V2 candidate side must be BUY or SELL')
    zone_lower = float(features['zone_lower'])
    zone_upper = float(features['zone_upper'])
    target_zone_lower = float(features['target_zone_lower'])
    target_zone_upper = float(features['target_zone_upper'])
    stop_price = float(features['stop_price'])
    target_price = float(features['target_price'])
    reward_risk = float(features['reward_risk'])
    touch_count = int(features['touch_count'])
    target_touch_count = int(features['target_touch_count'])
    target_score = int(features['target_score'])
    reaction_atr = float(features['reaction_atr'])
    role_flip = bool(features['role_flip'])
    trigger = str(features['trigger'])
    score = int(features['score'])
    if snapshot.atr <= 0 or not isfinite(snapshot.atr):
        raise ValueError('KEY_LEVEL_V2 snapshot ATR must be positive and finite')
    if (
        touch_count < 2
        or target_touch_count < 2
        or score < MIN_ZONE_SCORE
        or target_score < MIN_ZONE_SCORE
    ):
        raise ValueError('KEY_LEVEL_V2 candidate zones do not meet the quality floor')
    if trigger not in {'REJECTION', 'FALSE_BREAK', 'BREAK_RETEST'}:
        raise ValueError('KEY_LEVEL_V2 trigger is unsupported')
    numeric_values = (
        zone_lower,
        zone_upper,
        target_zone_lower,
        target_zone_upper,
        stop_price,
        target_price,
        reward_risk,
    )
    if not all(isfinite(value) for value in numeric_values):
        raise ValueError('KEY_LEVEL_V2 structural levels must be finite')
    if zone_lower >= zone_upper or target_zone_lower >= target_zone_upper:
        raise ValueError('KEY_LEVEL_V2 zones must have positive width')
    typed_side = 'BUY' if side == 'BUY' else 'SELL'
    if typed_side == 'BUY':
        valid_order = stop_price < snapshot.close < target_price < target_zone_lower
        valid_zones = zone_upper < target_zone_lower
    else:
        valid_order = target_zone_upper < target_price < snapshot.close < stop_price
        valid_zones = target_zone_upper < zone_lower
    if not valid_order or not valid_zones:
        raise ValueError('KEY_LEVEL_V2 structural levels are inconsistent with candidate side')
    if reward_risk < MIN_REWARD_RISK:
        raise ValueError('KEY_LEVEL_V2 structural reward/risk is below the minimum')
    stop_distance = abs(snapshot.close - stop_price)
    target_distance = abs(target_price - snapshot.close)
    trigger_labels = {
        'REJECTION': '触碰后收回',
        'FALSE_BREAK': '刺穿后收回',
        'BREAK_RETEST': '突破后回踩',
    }
    role_text = '，历史发生支撑压力互换' if role_flip else ''
    reason = (
        f'关键区域 {zone_lower:.2f}–{zone_upper:.2f}，{touch_count} 次独立触碰，'
        f'中位反应 {reaction_atr:.2f} ATR{role_text}；'
        f'当前为{trigger_labels.get(trigger, trigger)}，质量分 {score}；'
        f'下一关键区域 {target_zone_lower:.2f}–{target_zone_upper:.2f}'
        f'（{target_touch_count} 次触碰，质量分 {target_score}），成本后预估 R:R {reward_risk:.2f}'
    )
    return Signal(
        mode=ManualSignalMode.KEY_LEVEL_V2,
        strategy=ManualSignalMode.KEY_LEVEL_V2.value,
        side=typed_side,
        signal_time=snapshot.closed_at,
        signal_close=snapshot.close,
        atr_snapshot=snapshot.atr,
        stop_atr_multiple=stop_distance / snapshot.atr,
        target_atr_multiple=target_distance / snapshot.atr,
        stop_distance=stop_distance,
        target_distance=target_distance,
        estimated_stop_price=stop_price,
        estimated_target_price=target_price,
        environment_side=snapshot.environment_side or typed_side,
        filter_label=snapshot.filter_label,
        reason=reason,
        score=score,
        structural_risk=StructuralRisk(
            entry_zone_lower=zone_lower,
            entry_zone_upper=zone_upper,
            target_zone_lower=target_zone_lower,
            target_zone_upper=target_zone_upper,
            stop_price=stop_price,
            target_price=target_price,
            reference_reward_risk=reward_risk,
        ),
    )


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


def _build_order_flow_absorption_signal(
    snapshot: MarketSnapshot,
    features: Mapping[str, object],
) -> Signal:
    taker_buy_ratio = float(features['taker_buy_ratio'])
    oi_change = float(features['oi_change_45m'])
    taker_threshold = float(features['taker_ratio_threshold'])
    oi_threshold = float(features['oi_change_threshold'])
    funding_rate = float(features['funding_rate'])
    stop_distance = snapshot.atr * ORDER_FLOW_STOP_ATR_MULTIPLE
    target_distance = snapshot.atr * ORDER_FLOW_TARGET_ATR_MULTIPLE
    funding_text = '暂无已结算值' if pd.isna(funding_rate) else f'{funding_rate * 100:.4f}%'
    reason = (
        f'Taker {taker_buy_ratio * 100:.1f}%≥30日阈值 {taker_threshold * 100:.1f}%'
        f'，OI 45分钟 {oi_change * 100:.2f}%≥阈值 {oi_threshold * 100:.2f}%'
        f'，价格收弱；资金费率 {funding_text}'
    )
    return Signal(
        mode=ManualSignalMode.ORDER_FLOW_ABSORPTION_15M,
        strategy=ManualSignalMode.ORDER_FLOW_ABSORPTION_15M.value,
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
