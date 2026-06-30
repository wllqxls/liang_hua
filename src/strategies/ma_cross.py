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

from src.strategies.risk import build_long_risk_prices, calculate_fractional_order_size


class MovingAverageCross(Strategy):
    """均线金叉死叉策略。"""

    lookback = 30
    position_amount = 0.0
    leverage = 1.0
    take_profit_pct = 0.0
    stop_loss_pct = 0.0

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
        if self.fast_ma[-2] <= self.slow_ma[-2] and self.fast_ma[-1] > self.slow_ma[-1]:
            if not self.position:
                price = self.data.Close[-1]
                take_profit, stop_loss = build_long_risk_prices(price, self.take_profit_pct, self.stop_loss_pct)
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
        elif self.position and self.fast_ma[-2] >= self.slow_ma[-2] and self.fast_ma[-1] < self.slow_ma[-1]:
            self.position.close()
