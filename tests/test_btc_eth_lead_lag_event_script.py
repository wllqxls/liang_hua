from __future__ import annotations

import pandas as pd

from scripts.research_event_factors import (
    LeadLagResearchSlice,
    _lead_lag_gate_passed,
    write_btc_eth_lead_lag_report,
)


def _slice(year: int, *, net: float, ci_lower: float, pf: float) -> LeadLagResearchSlice:
    summary = pd.DataFrame(
        {
            'horizon': ['5m', '15m', '30m', '1h'],
            'samples': [300, 300, 300, 300],
            'positive_rate_pct': [51.0, 52.0, 53.0, 54.0],
            'average_gross_return': [0.002] * 4,
            'average_net_return': [net] * 4,
            'break_even_round_trip_cost': [0.002] * 4,
            'net_mean_ci_lower': [ci_lower] * 4,
            'net_mean_ci_upper': [0.001] * 4,
            'profit_factor': [pf] * 4,
        }
    )
    return LeadLagResearchSlice(
        year=year,
        status='COMPLETE_YEAR',
        events=300,
        side_counts={'BUY': 160, 'SELL': 140},
        dataset_path=None,
        summary=summary,
    )


def test_gate_requires_both_years_and_positive_primary_confidence_bound() -> None:
    passing = [_slice(2024, net=0.0006, ci_lower=0.0001, pf=1.2), _slice(2025, net=0.0006, ci_lower=0.0001, pf=1.2)]
    failing = [passing[0], _slice(2025, net=0.0006, ci_lower=-0.0001, pf=1.2)]

    assert _lead_lag_gate_passed(passing) is True
    assert _lead_lag_gate_passed(failing) is False


def test_report_displays_break_even_interval_and_no_strategy(tmp_path) -> None:
    output = tmp_path / 'lead-lag.md'

    write_btc_eth_lead_lag_report(
        [_slice(2024, net=0.0006, ci_lower=0.0001, pf=1.2), _slice(2025, net=0.0006, ci_lower=0.0001, pf=1.2)],
        output,
    )

    report = output.read_text(encoding='utf-8')
    assert '| 2024 | 15m | 300 | 52.00 | 0.2000 | 0.0600 | 0.2000 | [0.0100, 0.1000] | 1.200 |' in report
    assert '- Passed: `yes`.' in report
    assert '- Strategy generated: `no`.' in report
    assert '2026 remains unused' in report
