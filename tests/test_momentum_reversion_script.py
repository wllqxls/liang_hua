from __future__ import annotations

import pandas as pd

from scripts.research_momentum_reversion import (
    _calendar_year_slice,
    _research_verdict,
)


def test_calendar_slice_uses_event_timestamp_not_data_directory() -> None:
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


def test_low_conversion_or_small_sample_is_rejected_without_strategy() -> None:
    verdict, reasons = _research_verdict(samples=240, conversion_rate=0.09)

    assert verdict == 'REJECT_NO_STRATEGY'
    assert any('10%' in reason for reason in reasons)

    verdict, reasons = _research_verdict(samples=80, conversion_rate=0.20)

    assert verdict == 'REJECT_NO_STRATEGY'
    assert any('200' in reason for reason in reasons)
