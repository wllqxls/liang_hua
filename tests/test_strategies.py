from __future__ import annotations

from src.strategies.key_level_scoring import KeyLevelScoring
from src.strategies.ma_cross import MovingAverageCross
from src.strategies.risk import (
    build_long_risk_prices,
    build_risk_prices,
    calculate_fractional_order_size,
    estimate_liquidation_price,
    strong_context_trend_allows_side,
)
from src.strategies.rsi_reversion import RSIReversion
from src.strategies.sr_breakout import SRBreakout, SupportResistanceBreakout


class FakeSeries:
    def __init__(self, value: float) -> None:
        self._value = value

    def __getitem__(self, index: int) -> float:
        return self._value


class FakeContextData:
    def __init__(
        self,
        trend: float | None,
        strength: float | None,
        momentum: float | None = None,
        close: float | None = None,
        fast_ma: float | None = None,
    ) -> None:
        if trend is not None:
            self.ContextTrend = FakeSeries(trend)
        if strength is not None:
            self.ContextTrendStrength = FakeSeries(strength)
        if momentum is not None:
            self.ContextTrendMomentum = FakeSeries(momentum)
        if close is not None:
            self.ContextClose = FakeSeries(close)
        if fast_ma is not None:
            self.ContextFastMA = FakeSeries(fast_ma)


def test_sr_breakout_default_parameters() -> None:
    assert SRBreakout.lookback == 20
    assert SRBreakout.atr_mult == 2.0


def test_key_level_scoring_default_parameters() -> None:
    assert KeyLevelScoring.lookback == 20
    assert KeyLevelScoring.min_score == 5
    assert KeyLevelScoring.volume_confirm == 1.2
    assert KeyLevelScoring.wick_reject_ratio == 0.45


def test_support_resistance_alias_reuses_strategy() -> None:
    assert issubclass(SupportResistanceBreakout, SRBreakout)


def test_moving_average_cross_default_parameters() -> None:
    assert MovingAverageCross.lookback == 30


def test_rsi_reversion_default_parameters() -> None:
    assert RSIReversion.lookback == 14
    assert RSIReversion.lower == 30
    assert RSIReversion.upper == 70


def test_fractional_order_size_uses_margin_and_leverage() -> None:
    size = calculate_fractional_order_size(
        price=0.0006,
        equity=10,
        position_amount=3.3,
        leverage=5,
    )

    assert size == 27_500


def test_long_risk_prices_use_usdt_amounts() -> None:
    take_profit, stop_loss = build_long_risk_prices(
        price=100.0,
        position_amount=3.3,
        leverage=20,
        take_profit_amount=6.0,
        stop_loss_amount=2.0,
    )

    assert round(take_profit, 4) == 109.0909
    assert round(stop_loss, 4) == 96.9697


def test_short_risk_prices_use_usdt_amounts_and_liquidation_cap() -> None:
    take_profit, stop_loss = build_risk_prices(
        side="short",
        price=100.0,
        position_amount=3.3,
        leverage=20,
        take_profit_amount=6.0,
        stop_loss_amount=10.0,
    )

    assert round(take_profit, 4) == 90.9091
    assert round(stop_loss, 4) == 104.5


def test_liquidation_price_is_side_aware() -> None:
    assert estimate_liquidation_price("long", 100.0, 20, 0.005) == 95.5
    assert round(estimate_liquidation_price("short", 100.0, 20, 0.005), 4) == 104.5


def test_strong_context_trend_requires_alignment() -> None:
    data = FakeContextData(trend=1, strength=1.2, momentum=0.2, close=110, fast_ma=100)

    assert strong_context_trend_allows_side(data, 'long') is True
    assert strong_context_trend_allows_side(data, 'short') is False


def test_strong_context_trend_allows_strong_downtrend_short() -> None:
    data = FakeContextData(trend=-1, strength=1.2, momentum=-0.2, close=90, fast_ma=100)

    assert strong_context_trend_allows_side(data, 'short') is True
    assert strong_context_trend_allows_side(data, 'long') is False


def test_strong_context_trend_rejects_weak_or_missing_context() -> None:
    assert strong_context_trend_allows_side(
        FakeContextData(1, 0.99, 0.2, 110, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(1, None, 0.2, 110, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(None, 1.2, 0.2, 110, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(1, 1.2, None, 110, 100), 'long'
    ) is False


def test_strong_context_trend_rejects_reversing_momentum() -> None:
    assert strong_context_trend_allows_side(
        FakeContextData(1, 1.2, -0.1, 110, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(-1, 1.2, 0.1, 90, 100), 'short'
    ) is False


def test_strong_context_trend_rejects_wrong_price_position() -> None:
    assert strong_context_trend_allows_side(
        FakeContextData(1, 1.2, 0.2, 90, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(-1, 1.2, -0.2, 110, 100), 'short'
    ) is False
