from __future__ import annotations

import pytest

from src.backtest.diagnostics import analyze_trades


def test_analyze_trades_separates_market_pnl_from_execution_costs() -> None:
    diagnostics = analyze_trades(
        [
            {
                'pnl': 8.0,
                'entry_commission': 1.0,
                'exit_commission': 1.0,
                'funding_fee': 0.5,
                'exit_reason': 'TARGET',
                'side': 'long',
                'environment_1h': 'BUY',
                'filter_4h': 'FILTER_LONG',
            },
            {
                'pnl': -6.0,
                'entry_commission': 0.5,
                'exit_commission': 0.5,
                'funding_fee': -0.25,
                'exit_reason': 'STOP',
                'side': 'short',
                'environment_1h': 'SELL',
                'filter_4h': 'FILTER_NEUTRAL',
            },
        ]
    )

    assert diagnostics.trades == 2
    assert diagnostics.win_rate_pct == 50.0
    assert diagnostics.gross_pnl == pytest.approx(4.75)
    assert diagnostics.commission == pytest.approx(3.0)
    assert diagnostics.funding_cash_flow == pytest.approx(0.25)
    assert diagnostics.net_cost == pytest.approx(2.75)
    assert diagnostics.net_pnl == pytest.approx(2.0)
    assert diagnostics.average_net_pnl == pytest.approx(1.0)
    assert diagnostics.gross_profit_factor == pytest.approx(9.5 / 4.75)
    assert diagnostics.net_profit_factor == pytest.approx(8.0 / 6.0)
    assert diagnostics.cost_to_gross_profit_pct == pytest.approx(2.75 / 9.5 * 100)


def test_analyze_trades_builds_all_required_breakdowns() -> None:
    diagnostics = analyze_trades(
        [
            {
                'pnl': 2.0,
                'exit_reason': 'TARGET',
                'side': 'long',
                'environment_1h': 'BUY',
                'filter_4h': 'FILTER_LONG',
            },
            {
                'pnl': -1.0,
                'exit_reason': 'STOP',
                'side': 'long',
                'environment_1h': 'BUY',
                'filter_4h': 'FILTER_NEUTRAL',
            },
        ]
    )

    assert [item.label for item in diagnostics.by_exit_reason] == ['STOP', 'TARGET']
    assert [item.label for item in diagnostics.by_side] == ['long']
    assert [item.label for item in diagnostics.by_environment_1h] == ['BUY']
    assert [item.label for item in diagnostics.by_filter_4h] == [
        'FILTER_LONG',
        'FILTER_NEUTRAL',
    ]
    assert diagnostics.by_side[0].trades == 2
    assert diagnostics.by_side[0].net_pnl == pytest.approx(1.0)


def test_analyze_trades_handles_empty_or_legacy_trade_fields() -> None:
    empty = analyze_trades([])
    legacy = analyze_trades([{'pnl': -2.0}])

    assert empty.trades == 0
    assert empty.cost_to_gross_profit_pct is None
    assert legacy.gross_pnl == -2.0
    assert legacy.by_exit_reason[0].label == 'UNKNOWN'
