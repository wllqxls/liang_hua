from __future__ import annotations

import pandas as pd
import pytest

from src.research.event_factors import (
    FIXED_ROUND_TRIP_COST,
    build_hourly_extreme_reversion_dataset,
    summarize_hourly_extreme_reversion,
)


def _hour_frame() -> pd.DataFrame:
    index = pd.date_range('2025-01-01', periods=100, freq='1h', tz='UTC')
    open_price = pd.Series(100.0, index=index)
    close = pd.Series(100.0, index=index)
    close.iloc[22] = 95.0
    close.iloc[23] = 105.0
    open_price.iloc[22] = 95.0
    open_price.iloc[23] = 105.0
    open_price.iloc[40] = 100.0
    close.iloc[40] = 100.7
    open_price.iloc[41] = 100.7
    close.iloc[41] = 101.6
    open_price.iloc[42] = 101.6
    close.iloc[42] = 101.3
    open_price.iloc[43] = 101.3
    close.iloc[43] = 100.9
    high = pd.concat([open_price, close], axis=1).max(axis=1) + 0.2
    low = pd.concat([open_price, close], axis=1).min(axis=1) - 0.2
    return pd.DataFrame(
        {
            'Open': open_price,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': 100.0,
        },
        index=index,
    )


def test_two_large_hour_bodies_create_contrarian_event_and_two_hour_b() -> None:
    hour = _hour_frame()

    events = build_hourly_extreme_reversion_dataset(hour)

    event_time = hour.index[41] + pd.Timedelta(hours=1)
    row = events.loc[event_time]
    assert row['side'] == 'SELL'
    assert row['trigger'] == 'TWO_BAR'
    assert bool(row['reversed_1h']) is False
    assert bool(row['reversed_2h']) is True
    expected_gross = -(100.9 / 101.6 - 1)
    assert row['forward_return_2h'] == pytest.approx(expected_gross)
    assert row['forward_return_2h_net'] == pytest.approx(
        expected_gross - FIXED_ROUND_TRIP_COST
    )


def test_future_reversal_changes_outcomes_not_event_features() -> None:
    hour = _hour_frame()
    changed = hour.copy()
    changed.iloc[43, changed.columns.get_loc('Close')] = 102.0

    base = build_hourly_extreme_reversion_dataset(hour)
    changed_events = build_hourly_extreme_reversion_dataset(changed)
    event_time = hour.index[41] + pd.Timedelta(hours=1)
    feature_columns = ['side', 'trigger', 'atr', 'body_pct', 'two_bar_move_pct']

    assert base.loc[event_time, feature_columns].to_dict() == (
        changed_events.loc[event_time, feature_columns].to_dict()
    )
    assert base.loc[event_time, 'forward_return_2h'] != changed_events.loc[
        event_time,
        'forward_return_2h',
    ]


def test_hourly_summary_reports_b_conversion_net_average_and_pf() -> None:
    events = pd.DataFrame(
        {
            'reversed_1h': [True, False],
            'reversed_2h': [True, True],
            'forward_return_1h': [0.01, -0.01],
            'forward_return_1h_net': [0.0086, -0.0114],
            'forward_return_2h': [0.02, -0.01],
            'forward_return_2h_net': [0.0186, -0.0114],
        }
    )

    summary = summarize_hourly_extreme_reversion(events)

    one_hour = summary.loc[summary['horizon'] == '1h'].iloc[0]
    assert one_hour['samples'] == 2
    assert one_hour['reversal_rate_pct'] == 50.0
    assert one_hour['average_net_return'] == pytest.approx(-0.0014)
    assert one_hour['profit_factor'] == pytest.approx(0.0086 / 0.0114)
