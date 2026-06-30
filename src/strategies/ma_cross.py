"""
均线金叉死叉策略。

核心逻辑：
- 快线 = 最近 lookback / 2 根 K 线收盘价均线
- 慢线 = 最近 lookback 根 K 线收盘价均线
- 快线上穿慢线时买入
- 快线下穿慢线时平仓
"""

from backtesting import Strategy
import pandas as pd

from src.strategies.risk import (
    build_entry_tag,
    build_risk_prices,
    calculate_fractional_order_size,
    context_allows_side,
)


class MovingAverageCross(Strategy):
    """均线金叉死叉策略。"""

    lookback = 30
    position_amount = 0.0
    leverage = 1.0
    take_profit_amount = 0.0
    stop_loss_amount = 0.0
    maintenance_margin_rate = 0.005

    def init(self) -> None:
        """策略初始化——计算快慢均线。"""
        fast_window = max(2, self.lookback // 2)
        slow_window = max(fast_window + 1, self.lookback)
        self.fast_ma = self.I(
            lambda x: pd.Series(x).rolling(fast_window).mean(),
            self.data.Close,
            name="fast_ma",
            overlay=False,
        )
        self.slow_ma = self.I(
            lambda x: pd.Series(x).rolling(slow_window).mean(),
            self.data.Close,
            name="slow_ma",
            overlay=False,
        )

    def next(self) -> None:
        """每根 K 线触发一次——决策买卖。"""
        crossed_up = self.fast_ma[-2] <= self.slow_ma[-2] and self.fast_ma[-1] > self.slow_ma[-1]
        crossed_down = self.fast_ma[-2] >= self.slow_ma[-2] and self.fast_ma[-1] < self.slow_ma[-1]

        if self.position:
            if (self.position.is_long and crossed_down) or (self.position.is_short and crossed_up):
                self.position.close()
            return

        if crossed_up:
            self._open("long")
        elif crossed_down:
            self._open("short")

    def _open(self, side: str) -> None:
        price = self.data.Close[-1]
        if not context_allows_side(self.data, side, price):
            return
        reason = "快线上穿慢线" if side == "long" else "快线下穿慢线"
        tag = build_entry_tag(
            reason=reason,
            score=3,
            context={
                "fast_ma": round(float(self.fast_ma[-1]), 4),
                "slow_ma": round(float(self.slow_ma[-1]), 4),
            },
        )
        take_profit, stop_loss = build_risk_prices(
            side=side,
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
        if side == "short":
            if size is None:
                self.sell(tp=take_profit, sl=stop_loss, tag=tag)
            else:
                self.sell(size=size, tp=take_profit, sl=stop_loss, tag=tag)
        elif size is None:
            self.buy(tp=take_profit, sl=stop_loss, tag=tag)
        else:
            self.buy(size=size, tp=take_profit, sl=stop_loss, tag=tag)
