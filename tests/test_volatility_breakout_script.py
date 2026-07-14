from __future__ import annotations

import pandas as pd
import pytest

from scripts.research_volatility_breakout import (
    BreakoutMetrics,
    VolatilityBreakoutResearchSlice,
    _calendar_year_slice,
    _overall_metrics,
    write_volatility_breakout_report,
)


def test_calendar_slice_is_based_on_actual_event_timestamp() -> None:
    events = pd.DataFrame(
        {'value': [1, 2]},
        index=pd.DatetimeIndex(
            [
                pd.Timestamp('2025-12-31 23:55', tz='UTC'),
                pd.Timestamp('2026-01-01 00:00', tz='UTC'),
            ]
        ),
    )

    sliced = _calendar_year_slice(events, year=2026)

    assert sliced['value'].tolist() == [2]


def test_report_displays_exact_aggregate_profit_factor(tmp_path) -> None:
    events = pd.DataFrame(
        {
            'forward_return_1h': [0.01, -0.02],
            'forward_return_1h_net': [0.0086, -0.0214],
        }
    )
    metrics = _overall_metrics(events)
    assert metrics is not None
    assert metrics.profit_factor == pytest.approx(0.0086 / 0.0214)
    summary = pd.DataFrame(
        {
            'factor': ['direction'],
            'bucket': ['BUY'],
            'samples': [2],
            'average_gross_return': [-0.005],
            'average_net_return': [-0.0064],
            'win_rate_pct': [50.0],
            'profit_factor': [metrics.profit_factor],
            'meets_minimum_sample': [False],
        }
    )
    item = VolatilityBreakoutResearchSlice(
        symbol='BTC/USDT',
        year=2026,
        status='PARTIAL_YEAR',
        compression_events=10,
        breakout_events=2,
        conversion_rate=0.2,
        compression_dataset_path=None,
        breakout_dataset_path=None,
        one_hour_metrics=BreakoutMetrics(
            average_gross_return=metrics.average_gross_return,
            average_net_return=metrics.average_net_return,
            win_rate_pct=metrics.win_rate_pct,
            profit_factor=metrics.profit_factor,
        ),
        summary=summary,
    )
    output = tmp_path / 'report.md'

    write_volatility_breakout_report([item], output)

    assert 'Net Profit Factor | 0.402' in output.read_text(encoding='utf-8')
