"""
策略通用风控与仓位工具。
"""

from __future__ import annotations

from typing import Any, Literal


FRACTIONAL_UNIT = 1 / 100e6


def calculate_fractional_order_size(
    price: float,
    equity: float,
    position_amount: float,
    leverage: float,
) -> int | None:
    """计算 FractionalBacktest 可接受的下单数量。"""
    if price <= 0:
        return None

    if position_amount <= 0:
        return None

    margin_amount = min(position_amount, equity)
    notional_amount = margin_amount * max(leverage, 1)
    size = int(notional_amount / price)
    return size if size >= 1 else None


def build_long_risk_prices(
    price: float,
    position_amount: float,
    leverage: float,
    take_profit_amount: float,
    stop_loss_amount: float,
) -> tuple[float | None, float | None]:
    """根据目标盈亏金额计算多头止盈/止损价格。"""
    return build_risk_prices(
        side="long",
        price=price,
        position_amount=position_amount,
        leverage=leverage,
        take_profit_amount=take_profit_amount,
        stop_loss_amount=stop_loss_amount,
    )


def build_risk_prices(
    side: str,
    price: float,
    position_amount: float,
    leverage: float,
    take_profit_amount: float,
    stop_loss_amount: float,
    maintenance_margin_rate: float = 0.005,
) -> tuple[float | None, float | None]:
    """根据目标盈亏金额和强平近似值计算止盈/止损价格。"""
    notional_amount = position_amount * max(leverage, 1)
    if price <= 0 or notional_amount <= 0:
        return None, None

    take_profit_pct = take_profit_amount / notional_amount if take_profit_amount > 0 else 0
    stop_loss_pct = stop_loss_amount / notional_amount if stop_loss_amount > 0 else 0

    if side == "short":
        take_profit = price * (1 - take_profit_pct) if take_profit_pct > 0 else None
        stop_loss = price * (1 + stop_loss_pct) if stop_loss_pct > 0 else None
        liquidation = price * (1 + (1 / max(leverage, 1)) - maintenance_margin_rate)
        if stop_loss is None or stop_loss > liquidation:
            stop_loss = liquidation
    else:
        take_profit = price * (1 + take_profit_pct) if take_profit_pct > 0 else None
        stop_loss = price * (1 - stop_loss_pct) if stop_loss_pct > 0 else None
        liquidation = price * (1 - (1 / max(leverage, 1)) + maintenance_margin_rate)
        if stop_loss is None or stop_loss < liquidation:
            stop_loss = liquidation

    return take_profit, stop_loss


def estimate_liquidation_price(
    side: str,
    entry_price: float,
    leverage: float,
    maintenance_margin_rate: float,
) -> float:
    """估算逐仓强平价格。"""
    if side == "short":
        return entry_price * (1 + (1 / max(leverage, 1)) - maintenance_margin_rate)
    return entry_price * (1 - (1 / max(leverage, 1)) + maintenance_margin_rate)


def estimate_position_liquidation_price(
    *,
    side: Literal['BUY', 'SELL'],
    entry_price: float,
    quantity: float,
    collateral: float,
    maintenance_margin_rate: float,
) -> float:
    """Estimate one-position liquidation from the collateral backing that position."""
    if entry_price <= 0 or quantity <= 0 or collateral < 0:
        raise ValueError('liquidation inputs must be positive')
    if not 0 <= maintenance_margin_rate < 1:
        raise ValueError('maintenance margin rate must be between 0 and 1')
    notional_at_entry = quantity * entry_price
    if side == 'BUY':
        liquidation = (notional_at_entry - collateral) / (
            quantity * (1 - maintenance_margin_rate)
        )
        return max(0.0, liquidation)
    return (notional_at_entry + collateral) / (
        quantity * (1 + maintenance_margin_rate)
    )


def context_allows_side(data: object, side: str, price: float) -> bool:
    """根据高周期环境过滤方向；没有高周期字段时默认放行。"""
    trend = _latest_data_value(data, "ContextTrend")
    support = _latest_data_value(data, "ContextSupport")
    resistance = _latest_data_value(data, "ContextResistance")
    atr = _latest_data_value(data, "ContextATR")
    if trend is None:
        return True

    if side == "long" and trend > 0:
        return True
    if side == "short" and trend < 0:
        return True

    if support is None or resistance is None or atr is None or atr <= 0:
        return trend == 0

    near_support = abs(price - support) <= atr * 0.6
    near_resistance = abs(price - resistance) <= atr * 0.6
    if side == "long":
        return trend == 0 or near_support
    return trend == 0 or near_resistance


def strong_context_trend_allows_side(
    data: object,
    side: str,
    minimum_strength: float = 1.0,
) -> bool:
    """只在已收盘高周期的强趋势方向上允许入场。"""
    trend = _latest_data_value(data, 'ContextTrend')
    strength = _latest_data_value(data, 'ContextTrendStrength')
    momentum = _latest_data_value(data, 'ContextTrendMomentum')
    close = _latest_data_value(data, 'ContextClose')
    fast_ma = _latest_data_value(data, 'ContextFastMA')
    if any(value is None for value in [trend, strength, momentum, close, fast_ma]):
        return False
    if strength < minimum_strength:
        return False
    if side == 'long':
        return trend > 0 and momentum > 0 and close > fast_ma
    if side == 'short':
        return trend < 0 and momentum < 0 and close < fast_ma
    return False


def build_entry_tag(reason: str, score: float, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成可写入交易记录的入场标签。"""
    return {
        "reason": reason,
        "score": round(float(score), 2),
        "context": context or {},
    }


def _latest_data_value(data: object, column: str) -> float | None:
    try:
        values = getattr(data, column)
        value = float(values[-1])
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
    if value != value:
        return None
    return value
