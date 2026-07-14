from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.research_event_factors import (
    AbsorptionResearchSlice,
    _should_run_absorption_15m,
)


def _slice(symbol: str, year: int, average_net_return: float) -> AbsorptionResearchSlice:
    summary = pd.DataFrame(
        {
            'factor': ['overall'],
            'bucket': ['ALL'],
            'samples': [250],
            'average_gross_return': [average_net_return + 0.0014],
            'average_net_return': [average_net_return],
            'win_rate_pct': [55.0],
            'profit_factor': [1.2],
            'meets_minimum_sample': [True],
        }
    )
    return AbsorptionResearchSlice(
        symbol=symbol,
        timeframe='5m',
        year=year,
        status='COMPLETE_YEAR',
        event_a_count=250,
        event_b_count=100,
        conversion_rate=0.4,
        event_a_dataset_path=Path('a.csv'),
        event_b_dataset_path=Path('b.csv'),
        summary=summary,
    )


def test_15m_only_runs_when_all_four_five_minute_slices_are_positive() -> None:
    slices = [
        _slice('BTC/USDT', 2024, 0.001),
        _slice('BTC/USDT', 2025, 0.001),
        _slice('ETH/USDT', 2024, 0.001),
        _slice('ETH/USDT', 2025, 0.001),
    ]

    assert _should_run_absorption_15m(slices) is True

    slices[-1] = _slice('ETH/USDT', 2025, -0.0001)

    assert _should_run_absorption_15m(slices) is False
