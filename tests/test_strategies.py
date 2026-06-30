from __future__ import annotations

from src.strategies.ma_cross import MovingAverageCross
from src.strategies.risk import calculate_fractional_order_size
from src.strategies.rsi_reversion import RSIReversion
from src.strategies.sr_breakout import SRBreakout, SupportResistanceBreakout


def test_sr_breakout_default_parameters() -> None:
    assert SRBreakout.lookback == 20
    assert SRBreakout.atr_mult == 2.0


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
