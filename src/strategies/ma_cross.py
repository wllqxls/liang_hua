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


class MovingAverageCross(Strategy):
    """均线金叉死叉策略。"""

    lookback = 30

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
                self.buy()
        elif self.position and self.fast_ma[-2] >= self.slow_ma[-2] and self.fast_ma[-1] < self.slow_ma[-1]:
            self.position.close()
