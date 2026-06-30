"""
支撑位阻力位突破策略。

核心逻辑：
- 支撑位 = 最近 N 根 K 线的最低价
- 阻力位 = 最近 N 根 K 线的最高价
- 收盘价突破阻力位 → 买入
- 收盘价跌破支撑位 → 卖出

这是一个经典的趋势跟踪策略：价格突破近期高点说明上涨趋势确认，跌破近期低点说明下跌趋势确认。

可调参数：
    lookback: 回溯多少根 K 线计算支撑/阻力（默认 20）
    atr_mult: ATR 倍数止损（默认 2.0）
"""

from backtesting import Strategy
import pandas as pd

from src.strategies.risk import build_risk_prices, calculate_fractional_order_size


class SRBreakout(Strategy):
    """支撑阻力突破策略。"""

    # 可调参数
    lookback = 20       # 回溯窗口
    atr_mult = 2.0      # ATR 止损倍数
    position_amount = 0.0
    leverage = 1.0
    take_profit_amount = 0.0
    stop_loss_amount = 0.0
    maintenance_margin_rate = 0.005

    def init(self) -> None:
        """策略初始化——计算指标。"""
        # 阻力位（过去 N 根 K 线的最高价，不包括当前）
        self.resistance = self.I(
            lambda x: pd.Series(x).rolling(self.lookback).max().shift(1),
            self.data.High,
            name="resistance",
            overlay=False,
        )
        # 支撑位（过去 N 根 K 线的最低价，不包括当前）
        self.support = self.I(
            lambda x: pd.Series(x).rolling(self.lookback).min().shift(1),
            self.data.Low,
            name="support",
            overlay=False,
        )

    def next(self) -> None:
        """每根 K 线触发一次——决策买卖。"""
        price = self.data.Close[-1]

        if self.position:
            return

        if price > self.resistance[-1]:
            take_profit, stop_loss = build_risk_prices(
                side="long",
                price=price,
                position_amount=self.position_amount,
                leverage=self.leverage,
                take_profit_amount=self.take_profit_amount,
                stop_loss_amount=self.stop_loss_amount,
                maintenance_margin_rate=self.maintenance_margin_rate,
            )
            size = calculate_fractional_order_size(
                price=price,
                equity=self.equity,
                position_amount=self.position_amount,
                leverage=self.leverage,
            )
            if size is None:
                self.buy(tp=take_profit, sl=stop_loss)
            else:
                self.buy(size=size, tp=take_profit, sl=stop_loss)
        elif price < self.support[-1]:
            take_profit, stop_loss = build_risk_prices(
                side="short",
                price=price,
                position_amount=self.position_amount,
                leverage=self.leverage,
                take_profit_amount=self.take_profit_amount,
                stop_loss_amount=self.stop_loss_amount,
                maintenance_margin_rate=self.maintenance_margin_rate,
            )
            size = calculate_fractional_order_size(
                price=price,
                equity=self.equity,
                position_amount=self.position_amount,
                leverage=self.leverage,
            )
            if size is None:
                self.sell(tp=take_profit, sl=stop_loss)
            else:
                self.sell(size=size, tp=take_profit, sl=stop_loss)


# ============================================================
# 别名，方便导入
# ============================================================

class SupportResistanceBreakout(SRBreakout):
    """支撑位阻力位突破策略（中文别名）。"""
    pass
