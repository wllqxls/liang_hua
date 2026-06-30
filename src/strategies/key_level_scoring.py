"""
关键位评分策略。

支撑阻力只用于定位关键价格，真正方向由真假突破评分决定：
- 真突破阻力：偏做多
- 假突破阻力：偏做空
- 真跌破支撑：偏做空
- 假跌破支撑：偏做多
- 分数不够：不交易
"""

from __future__ import annotations

from backtesting import Strategy
import pandas as pd

from src.strategies.risk import build_risk_prices, calculate_fractional_order_size


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    """计算 ATR 波动率。"""
    high_series = pd.Series(high)
    low_series = pd.Series(low)
    close_series = pd.Series(close)
    prev_close = close_series.shift(1)
    true_range = pd.concat(
        [
            high_series - low_series,
            (high_series - prev_close).abs(),
            (low_series - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window).mean()


class KeyLevelScoring(Strategy):
    """关键位真假突破评分策略。"""

    lookback = 20
    trend_fast = 10
    trend_slow = 30
    atr_window = 14
    volume_window = 20
    min_score = 5
    min_score_gap = 1
    break_buffer_atr = 0.15
    volume_confirm = 1.2
    wick_reject_ratio = 0.45
    position_amount = 0.0
    leverage = 1.0
    take_profit_amount = 0.0
    stop_loss_amount = 0.0
    maintenance_margin_rate = 0.005

    def init(self) -> None:
        """初始化关键位、趋势、成交量和波动率指标。"""
        self.resistance = self.I(
            lambda values: pd.Series(values).rolling(self.lookback).max().shift(1),
            self.data.High,
            name="resistance",
            overlay=False,
        )
        self.support = self.I(
            lambda values: pd.Series(values).rolling(self.lookback).min().shift(1),
            self.data.Low,
            name="support",
            overlay=False,
        )
        self.fast_ma = self.I(
            lambda values: pd.Series(values).rolling(self.trend_fast).mean(),
            self.data.Close,
            name="fast_ma",
            overlay=False,
        )
        self.slow_ma = self.I(
            lambda values: pd.Series(values).rolling(self.trend_slow).mean(),
            self.data.Close,
            name="slow_ma",
            overlay=False,
        )
        self.volume_ma = self.I(
            lambda values: pd.Series(values).rolling(self.volume_window).mean(),
            self.data.Volume,
            name="volume_ma",
            overlay=False,
        )
        self.atr = self.I(
            lambda high, low, close: calculate_atr(high, low, close, self.atr_window),
            self.data.High,
            self.data.Low,
            self.data.Close,
            name="atr",
            overlay=False,
        )

    def next(self) -> None:
        """每根 K 线触发一次，按评分决定做多、做空或不交易。"""
        signal = self._score_signal()
        if signal is None:
            return

        side, _, _ = signal
        if self.position:
            if (self.position.is_long and side == "short") or (self.position.is_short and side == "long"):
                self.position.close()
            return

        self._open(side)

    def _score_signal(self) -> tuple[str, int, str] | None:
        resistance = float(self.resistance[-1])
        support = float(self.support[-1])
        atr = float(self.atr[-1])
        volume_ma = float(self.volume_ma[-1])
        if pd.isna(resistance) or pd.isna(support) or pd.isna(atr) or pd.isna(volume_ma):
            return None
        if resistance <= 0 or support <= 0 or atr <= 0 or volume_ma <= 0:
            return None

        open_ = float(self.data.Open[-1])
        high = float(self.data.High[-1])
        low = float(self.data.Low[-1])
        close = float(self.data.Close[-1])
        prev_close = float(self.data.Close[-2])
        volume = float(self.data.Volume[-1])
        candle_range = max(high - low, 1e-12)
        upper_wick = (high - max(open_, close)) / candle_range
        lower_wick = (min(open_, close) - low) / candle_range
        volume_ratio = volume / volume_ma
        buffer = atr * self.break_buffer_atr
        trend_up = float(self.fast_ma[-1]) > float(self.slow_ma[-1])
        trend_down = float(self.fast_ma[-1]) < float(self.slow_ma[-1])

        long_score = 0
        short_score = 0
        long_reason = ""
        short_reason = ""

        if close > resistance + buffer:
            long_score += 2
            long_reason = "真突破阻力做多"
            if prev_close > resistance:
                long_score += 1
            if upper_wick <= self.wick_reject_ratio:
                long_score += 1
            else:
                long_score -= 2
        if high > resistance + buffer and close <= resistance:
            short_score += 2
            short_reason = "阻力假突破做空"
            if upper_wick >= self.wick_reject_ratio:
                short_score += 2

        if close < support - buffer:
            short_score += 2
            short_reason = "真跌破支撑做空"
            if prev_close < support:
                short_score += 1
            if lower_wick <= self.wick_reject_ratio:
                short_score += 1
            else:
                short_score -= 2
        if low < support - buffer and close >= support:
            long_score += 2
            long_reason = "支撑假跌破做多"
            if lower_wick >= self.wick_reject_ratio:
                long_score += 2

        if volume_ratio >= self.volume_confirm:
            if long_reason:
                long_score += 2
            if short_reason:
                short_score += 2
        if trend_up:
            long_score += 1
            short_score -= 1
        if trend_down:
            short_score += 1
            long_score -= 1

        if long_score >= self.min_score and long_score >= short_score + self.min_score_gap:
            return "long", long_score, long_reason or "关键位评分做多"
        if short_score >= self.min_score and short_score >= long_score + self.min_score_gap:
            return "short", short_score, short_reason or "关键位评分做空"
        return None

    def _open(self, side: str) -> None:
        price = float(self.data.Close[-1])
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
