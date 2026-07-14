from __future__ import annotations

from scripts.research_pullback_confirmation import evaluate_research_gate


def _metrics(**overrides: float) -> dict[str, float]:
    return {
        'avg_window_return_pct': 1.0,
        'worst_window_return_pct': -5.0,
        'annual_return_pct': 12.0,
        'max_drawdown_pct': -10.0,
        'profit_factor': 1.2,
        'annual_trades': 60.0,
    } | overrides


def test_research_gate_requires_stricter_profit_factor_and_window_breadth() -> None:
    passed, reasons = evaluate_research_gate(_metrics(), positive_windows=8)

    assert passed is True
    assert reasons == ()

    passed, reasons = evaluate_research_gate(
        _metrics(profit_factor=1.14),
        positive_windows=7,
    )

    assert passed is False
    assert 'cost-after Profit Factor is below 1.15' in reasons
    assert 'fewer than 8 of 12 independent windows are positive' in reasons
