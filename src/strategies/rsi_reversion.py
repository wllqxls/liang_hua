"""
RSI 超卖反弹策略。

核心逻辑：
- RSI 低于 30 视为超卖，尝试买入
- RSI 高于 70 视为反弹过热，平仓
- 持仓亏损超过 5% 时止损
"""

from backtesting import Strategy
import pandas as pd

from src.strategies.risk import build_risk_prices, calculate_fractional_order_size, context_allows_side


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
    take_profit_amount = 0.0
    stop_loss_amount = 0.0
    maintenance_margin_rate = 0.005

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
            if (self.position.is_long and self.rsi[-1] > self.upper) or (
                self.position.is_short and self.rsi[-1] < self.lower
            ):
                self.position.close()
            return

        if self.rsi[-1] < self.lower:
            self._open("long")
        elif self.rsi[-1] > self.upper:
            self._open("short")

    def _open(self, side: str) -> None:
        price = self.data.Close[-1]
        if not context_allows_side(self.data, side, price):
            return
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
                self.sell(tp=take_profit, sl=stop_loss)
            else:
                self.sell(size=size, tp=take_profit, sl=stop_loss)
        elif size is None:
            self.buy(tp=take_profit, sl=stop_loss)
        else:
            self.buy(size=size, tp=take_profit, sl=stop_loss)
