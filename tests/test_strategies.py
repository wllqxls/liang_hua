from __future__ import annotations

from src.strategies.sr_breakout import SRBreakout, SupportResistanceBreakout


def test_sr_breakout_default_parameters() -> None:
    assert SRBreakout.lookback == 20
    assert SRBreakout.atr_mult == 2.0


def test_support_resistance_alias_reuses_strategy() -> None:
    assert issubclass(SupportResistanceBreakout, SRBreakout)
