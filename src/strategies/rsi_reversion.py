"""
RSI 超卖反弹策略。

核心逻辑：
- RSI 低于 30 视为超卖，尝试买入
- RSI 高于 70 视为反弹过热，平仓
- 持仓亏损超过 5% 时止损
"""

from backtesting import Strategy
import pandas as pd


def calculate_rsi(values: pd.Series, window: int) -> pd.Series:
    """计算 RSI 指标。"""
    series = pd.Series(values)
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = -delta.clip(upper=0).rolling(window).mean()
    rs = gain / loss.where(loss != 0)
    return 100 - (100 / (1 + rs))


class RSIReversion(Strategy):
    """RSI 超卖反弹策略。"""

    lookback = 14
    lower = 30
    upper = 70

    def init(self) -> None:
        """策略初始化——计算 RSI。"""
        self.rsi = self.I(
            lambda x: calculate_rsi(x, self.lookback),
            self.data.Close,
            name="rsi",
        )

    def next(self) -> None:
        """每根 K 线触发一次——决策买卖。"""
        if self.position:
            if self.rsi[-1] > self.upper or self.position.pl_pct <= -5.0:
                self.position.close()
            return

        if self.rsi[-1] < self.lower:
            self.buy()
