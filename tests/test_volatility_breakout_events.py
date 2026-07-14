from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.volatility_breakout_events import (
    FIXED_ROUND_TRIP_COST,
    build_volatility_breakout_event_study,
    summarize_breakout_buckets,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    entry_index = pd.date_range('2026-01-03', periods=330, freq='5min', tz='UTC')
    entry = pd.DataFrame(
        {
            'Open': 100.0,
            'High': 102.0,
            'Low': 98.0,
            'Close': 100.0,
            'Volume': 100.0,
        },
        index=entry_index,
    )
    entry.iloc[50:, entry.columns.get_loc('High')] = 100.1
    entry.iloc[50:, entry.columns.get_loc('Low')] = 99.9
    breakout_index = 108
    entry.iloc[breakout_index, entry.columns.get_loc('Open')] = 100.0
    entry.iloc[breakout_index, entry.columns.get_loc('High')] = 103.2
    entry.iloc[breakout_index, entry.columns.get_loc('Low')] = 99.8
    entry.iloc[breakout_index, entry.columns.get_loc('Close')] = 103.0
    entry.iloc[breakout_index + 12, entry.columns.get_loc('Close')] = 105.0
    entry.iloc[breakout_index + 12, entry.columns.get_loc('High')] = 105.1
    entry.iloc[breakout_index + 12, entry.columns.get_loc('Low')] = 99.9

    hour_index = pd.date_range('2026-01-01', periods=100, freq='1h', tz='UTC')
    hour_close = np.tile([99.5, 100.5], 50)
    hour = pd.DataFrame(
        {
            'Open': hour_close,
            'High': hour_close + 0.5,
            'Low': hour_close - 0.5,
            'Close': hour_close,
            'Volume': 100.0,
        },
        index=hour_index,
    )
    return entry, hour


def test_study_matches_one_compression_to_one_later_directional_breakout() -> None:
    entry, hour = _frames()

    study = build_volatility_breakout_event_study(entry, hour)

    breakout_time = entry.index[108] + pd.Timedelta(minutes=5)
    assert len(study.compression_events) >= 1
    assert len(study.breakout_events) == 1
    row = study.breakout_events.loc[breakout_time]
    assert row['side'] == 'BUY'
    assert 1 <= row['bars_since_compression'] <= 12
    assert row['forward_return_1h'] == pytest.approx(105.0 / 103.0 - 1)
    assert row['forward_return_1h_net'] == pytest.approx(
        105.0 / 103.0 - 1 - FIXED_ROUND_TRIP_COST
    )
    assert study.compression_events['converted_to_breakout'].sum() == 1


def test_future_prices_do_not_change_compression_or_breakout_features() -> None:
    entry, hour = _frames()
    changed = entry.copy()
    changed.iloc[120, changed.columns.get_loc('Close')] = 110.0
    changed.iloc[120, changed.columns.get_loc('High')] = 110.1

    base = build_volatility_breakout_event_study(entry, hour)
    changed_study = build_volatility_breakout_event_study(changed, hour)
    breakout_time = entry.index[108] + pd.Timedelta(minutes=5)
    feature_columns = [
        'side',
        'compression_ratio',
        'mid_distance_ratio',
        'bars_since_compression',
        'bb_upper_1h',
        'bb_lower_1h',
    ]

    assert base.breakout_events.loc[breakout_time, feature_columns].to_dict() == (
        changed_study.breakout_events.loc[breakout_time, feature_columns].to_dict()
    )
    assert base.breakout_events.loc[breakout_time, 'forward_return_1h'] != (
        changed_study.breakout_events.loc[breakout_time, 'forward_return_1h']
    )


def test_breakout_summary_includes_profit_factor_and_minimum_sample_marker() -> None:
    events = pd.DataFrame(
        {
            'side': ['BUY', 'BUY', 'SELL', 'SELL', 'BUY', 'SELL'],
            'compression_ratio': [0.50, 0.55, 0.60, 0.65, 0.70, 0.75],
            'mid_distance_ratio': [0.01, 0.03, 0.05, 0.07, 0.09, 0.11],
            'forward_return_1h': [0.01, -0.01, 0.02, -0.02, 0.01, 0.03],
            'forward_return_1h_net': [0.0086, -0.0114, 0.0186, -0.0214, 0.0086, 0.0286],
        }
    )

    summary = summarize_breakout_buckets(events)

    assert set(summary['factor']) == {
        'direction',
        'compression_tertile',
        'mid_distance_tertile',
    }
    buy_row = summary.loc[
        (summary['factor'] == 'direction') & (summary['bucket'] == 'BUY')
    ].iloc[0]
    assert buy_row['profit_factor'] == pytest.approx(0.0172 / 0.0114)
    assert bool(buy_row['meets_minimum_sample']) is False
