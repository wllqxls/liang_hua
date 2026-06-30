"""
RSI 超卖反弹策略。

核心逻辑：
- RSI 低于 30 视为超卖，尝试买入
- RSI 高于 70 视为反弹过热，平仓
- 持仓亏损超过 5% 时止损
"""

from backtesting import Strategy
import pandas as pd

from src.strategies.risk import build_long_risk_prices, calculate_fractional_order_size


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
    position_amount = 0.0
    leverage = 1.0
    take_profit_pct = 0.0
    stop_loss_pct = 5.0

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
            if self.rsi[-1] > self.upper or (self.stop_loss_pct <= 0 and self.position.pl_pct <= -5.0):
                self.position.close()
            return

        if self.rsi[-1] < self.lower:
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
