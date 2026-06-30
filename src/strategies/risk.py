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
    take_profit_pct: float,
    stop_loss_pct: float,
) -> tuple[float | None, float | None]:
    """根据当前价格计算多头止盈/止损价格。"""
    take_profit = price * (1 + take_profit_pct / 100) if take_profit_pct > 0 else None
    stop_loss = price * (1 - stop_loss_pct / 100) if stop_loss_pct > 0 else None
    return take_profit, stop_loss
