from __future__ import annotations

import pandas as pd

from scripts.research_event_factors import (
    HourlyExtremeReversionSlice,
    write_hourly_extreme_reversion_report,
)


def test_report_contains_both_horizons_cost_and_trigger_counts(tmp_path) -> None:
    summary = pd.DataFrame(
        {
            'horizon': ['1h', '2h'],
            'samples': [250, 250],
            'reversal_rate_pct': [40.0, 55.0],
            'average_gross_return': [0.001, 0.002],
            'average_net_return': [-0.0004, 0.0006],
            'profit_factor': [0.8, 1.1],
        }
    )
    research_slice = HourlyExtremeReversionSlice(
        symbol='BTC/USDT',
        year=2024,
        status='COMPLETE_YEAR',
        events=250,
        trigger_counts={'TWO_BAR': 200, 'BOLLINGER': 50},
        dataset_path=None,
        summary=summary,
    )
    output = tmp_path / 'hourly.md'

    write_hourly_extreme_reversion_report([research_slice], output)

    report = output.read_text(encoding='utf-8')
    assert 'Fixed complete round-trip cost: `0.0014`' in report
    assert '| BTC/USDT 2024 | 1h | 250 |' in report
    assert '| BTC/USDT 2024 | 2h | 250 |' in report
    assert 'BOLLINGER=50' in report
    assert 'TWO_BAR=200' in report
