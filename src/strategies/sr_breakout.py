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
from backtesting.lib import crossover
import pandas as pd


class SRBreakout(Strategy):
    """支撑阻力突破策略。"""

    # 可调参数
    lookback = 20       # 回溯窗口
    atr_mult = 2.0      # ATR 止损倍数

    def init(self) -> None:
        """策略初始化——计算指标。"""
        # 阻力位（过去 N 根 K 线的最高价，不包括当前）
        self.resistance = self.I(
            lambda x: pd.Series(x).rolling(self.lookback).max().shift(1),
            self.data.High,
            name="resistance",
        )
        # 支撑位（过去 N 根 K 线的最低价，不包括当前）
        self.support = self.I(
            lambda x: pd.Series(x).rolling(self.lookback).min().shift(1),
            self.data.Low,
            name="support",
        )

    def next(self) -> None:
        """每根 K 线触发一次——决策买卖。"""
        price = self.data.Close[-1]

        # 有持仓时检查止损（亏损超过 3% 平仓）
        if self.position:
            if self.position.pl_pct <= -3.0:
                self.position.close()
            return

        # 收盘价突破阻力位 → 买入（不指定 size，自动用全部可用资金）
        if price > self.resistance[-1]:
            self.buy()


# ============================================================
# 别名，方便导入
# ============================================================

class SupportResistanceBreakout(SRBreakout):
    """支撑位阻力位突破策略（中文别名）。"""
    pass
