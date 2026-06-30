"""
策略通用风控与仓位工具。
"""

from __future__ import annotations


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
