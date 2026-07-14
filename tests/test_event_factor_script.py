from __future__ import annotations

import pandas as pd

from scripts.research_event_factors import (
    _calendar_year_slice,
    _covers_calendar_year,
)


def test_calendar_slice_uses_event_timestamps_not_directory_labels() -> None:
    events = pd.DataFrame(
        {'value': [1, 2, 3]},
        index=pd.DatetimeIndex(
            [
                pd.Timestamp('2025-12-31 23:55', tz='UTC'),
                pd.Timestamp('2026-01-01 00:00', tz='UTC'),
                pd.Timestamp('2026-07-01 00:00', tz='UTC'),
            ]
        ),
    )

    sliced = _calendar_year_slice(events, year=2026)

    assert sliced['value'].tolist() == [2, 3]


def test_complete_year_requires_actual_calendar_coverage() -> None:
    rolling_window = pd.DataFrame(
        index=pd.date_range('2025-07-14', '2026-07-14', freq='5min', tz='UTC')
    )
    full_2025 = pd.DataFrame(
        index=pd.date_range('2025-01-01', '2025-12-31 23:55', freq='5min', tz='UTC')
    )

    assert _covers_calendar_year(rolling_window, year=2025) is False
    assert _covers_calendar_year(rolling_window, year=2026) is False
    assert _covers_calendar_year(full_2025, year=2025) is True
