from __future__ import annotations

import pandas as pd
import pytest

from src.research.event_factors import (
    FIXED_ROUND_TRIP_COST,
    build_trend_inertia_event_dataset,
    summarize_trend_inertia_horizons,
)


def _five_minute_frame() -> pd.DataFrame:
    index = pd.date_range('2025-01-01', periods=130, freq='5min', tz='UTC')
    close = pd.Series(100.0, index=index)
    close.iloc[58] = 100.15
    close.iloc[59] = 100.30
    close.iloc[60] = 100.50
    close.iloc[61] = 100.60
    close.iloc[62] = 100.65
    close.iloc[63] = 100.70
    close.iloc[72] = 100.80
    return pd.DataFrame(
        {
            'Open': close.shift(1).fillna(100.0),
            'High': close + 0.1,
            'Low': close - 0.1,
            'Close': close,
            'Volume': 100.0,
        },
        index=index,
    )


def test_trend_event_records_first_threshold_crossing_and_three_horizons() -> None:
    five_minute = _five_minute_frame()

    events = build_trend_inertia_event_dataset(
        five_minute,
        five_minute,
        timeframe='5m',
    )

    event_time = five_minute.index[60] + pd.Timedelta(minutes=5)
    row = events.loc[event_time]
    assert len(events) == 1
    assert row['side'] == 'BUY'
    assert row['streak_bars'] == 3
    assert row['cumulative_return_3'] == pytest.approx(0.005)
    assert row['forward_return_5m'] == pytest.approx(100.60 / 100.50 - 1)
    assert row['forward_return_15m'] == pytest.approx(100.70 / 100.50 - 1)
    assert row['forward_return_1h'] == pytest.approx(100.80 / 100.50 - 1)
    assert row['forward_return_1h_net'] == pytest.approx(
        100.80 / 100.50 - 1 - FIXED_ROUND_TRIP_COST
    )


def test_future_prices_only_change_labels_not_trend_event_features() -> None:
    five_minute = _five_minute_frame()
    changed = five_minute.copy()
    changed.iloc[72, changed.columns.get_loc('Close')] = 99.0

    base = build_trend_inertia_event_dataset(
        five_minute,
        five_minute,
        timeframe='5m',
    )
    changed_events = build_trend_inertia_event_dataset(
        changed,
        changed,
        timeframe='5m',
    )
    event_time = five_minute.index[60] + pd.Timedelta(minutes=5)
    feature_columns = ['side', 'streak_bars', 'cumulative_return_3', 'event_direction']

    assert base.loc[event_time, feature_columns].to_dict() == (
        changed_events.loc[event_time, feature_columns].to_dict()
    )
    assert base.loc[event_time, 'forward_return_1h'] != changed_events.loc[
        event_time,
        'forward_return_1h',
    ]


def test_horizon_summary_reports_conversion_net_average_and_profit_factor() -> None:
    events = pd.DataFrame(
        {
            'forward_return_5m': [0.01, -0.01],
            'forward_return_5m_net': [0.0086, -0.0114],
            'forward_return_15m': [0.02, -0.02],
            'forward_return_15m_net': [0.0186, -0.0214],
            'forward_return_1h': [0.03, -0.01],
            'forward_return_1h_net': [0.0286, -0.0114],
        }
    )

    summary = summarize_trend_inertia_horizons(events)

    five_minute = summary.loc[summary['horizon'] == '5m'].iloc[0]
    assert five_minute['samples'] == 2
    assert five_minute['conversion_rate_pct'] == 50.0
    assert five_minute['average_net_return'] == pytest.approx(-0.0014)
    assert five_minute['profit_factor'] == pytest.approx(0.0086 / 0.0114)
