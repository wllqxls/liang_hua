from __future__ import annotations

import pandas as pd

from scripts.research_event_factors import (
    TrendInertiaResearchSlice,
    write_trend_inertia_report,
)


def _slice(timeframe: str) -> TrendInertiaResearchSlice:
    summary = pd.DataFrame(
        {
            'horizon': ['5m', '15m', '1h'],
            'samples': [300, 300, 300],
            'conversion_rate_pct': [51.0, 52.0, 53.0],
            'average_gross_return': [0.001, 0.002, 0.003],
            'average_net_return': [-0.0004, 0.0006, 0.0016],
            'profit_factor': [0.8, 1.1, 1.2],
        }
    )
    return TrendInertiaResearchSlice(
        symbol='BTC/USDT',
        timeframe=timeframe,
        year=2024,
        status='COMPLETE_YEAR',
        events=300,
        dataset_path=None,
        summary=summary,
    )


def test_report_has_separate_five_and_fifteen_minute_tables(tmp_path) -> None:
    output = tmp_path / 'trend.md'

    write_trend_inertia_report([_slice('5m'), _slice('15m')], output)

    report = output.read_text(encoding='utf-8')
    assert '## 5m event results' in report
    assert '## 15m event results' in report
    assert report.count('BTC/USDT 2024') == 6
