from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.event_factors import (
    FIXED_ROUND_TRIP_COST,
    build_key_level_event_dataset,
    summarize_one_hour_factor_buckets,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    entry_index = pd.date_range('2026-01-01', periods=130, freq='5min', tz='UTC')
    entry = pd.DataFrame(
        {
            'Open': 100.0,
            'High': 101.0,
            'Low': 99.0,
            'Close': 100.0,
            'Volume': 100.0,
        },
        index=entry_index,
    )
    event_index = 60
    entry.iloc[event_index, entry.columns.get_loc('Open')] = 99.5
    entry.iloc[event_index, entry.columns.get_loc('High')] = 101.0
    entry.iloc[event_index, entry.columns.get_loc('Low')] = 98.0
    entry.iloc[event_index, entry.columns.get_loc('Close')] = 100.5
    entry.iloc[event_index, entry.columns.get_loc('Volume')] = 200.0
    entry.iloc[event_index + 12, entry.columns.get_loc('Close')] = 102.0
    entry.iloc[event_index + 12, entry.columns.get_loc('High')] = 102.0
    entry.iloc[event_index + 12, entry.columns.get_loc('Low')] = 99.0

    hour_index = pd.date_range('2025-12-31', periods=25, freq='1h', tz='UTC')
    hour_close = np.linspace(80.0, 104.0, len(hour_index))
    hour = pd.DataFrame(
        {
            'Open': hour_close - 0.5,
            'High': hour_close + 1,
            'Low': hour_close - 1,
            'Close': hour_close,
            'Volume': 100.0,
        },
        index=hour_index,
    )
    four_hour_index = pd.date_range(
        '2025-12-27 04:00',
        periods=30,
        freq='4h',
        tz='UTC',
    )
    four_hour_close = np.linspace(80.0, 109.0, len(four_hour_index))
    four_hour = pd.DataFrame(
        {
            'Open': four_hour_close - 0.5,
            'High': four_hour_close + 1,
            'Low': four_hour_close - 1,
            'Close': four_hour_close,
            'Volume': 100.0,
        },
        index=four_hour_index,
    )
    return entry, hour, four_hour


def test_event_dataset_freezes_known_features_and_adds_future_return_labels() -> None:
    entry, hour, four_hour = _frames()

    events = build_key_level_event_dataset(
        entry,
        hour,
        four_hour,
        timeframe='5m',
    )

    event_time = entry.index[60] + pd.Timedelta(minutes=5)
    row = events.loc[event_time]
    expected_gross = 102.0 / 100.5 - 1

    assert row['side'] == 'BUY'
    assert row['volume_ratio'] == pytest.approx(2.0)
    assert row['breach_atr'] > 0
    assert row['filter_4h'] == 'FILTER_LONG'
    assert row['forward_return_1h'] == pytest.approx(expected_gross)
    assert row['forward_return_1h_net'] == pytest.approx(
        expected_gross - FIXED_ROUND_TRIP_COST
    )


def test_future_price_changes_do_not_change_event_features() -> None:
    entry, hour, four_hour = _frames()
    changed = entry.copy()
    changed.iloc[72, changed.columns.get_loc('Close')] = 110.0
    changed.iloc[72, changed.columns.get_loc('High')] = 110.0

    base_events = build_key_level_event_dataset(entry, hour, four_hour, timeframe='5m')
    changed_events = build_key_level_event_dataset(
        changed,
        hour,
        four_hour,
        timeframe='5m',
    )
    event_time = entry.index[60] + pd.Timedelta(minutes=5)
    feature_columns = [
        'side',
        'breach_atr',
        'body_atr',
        'atr_pct',
        'rsi',
        'volume_ratio',
        'environment_1h',
        'filter_4h',
    ]

    assert base_events.loc[event_time, feature_columns].to_dict() == (
        changed_events.loc[event_time, feature_columns].to_dict()
    )
    assert base_events.loc[event_time, 'forward_return_1h'] != changed_events.loc[
        event_time,
        'forward_return_1h',
    ]


def test_ambiguous_two_sided_break_is_excluded() -> None:
    entry, hour, four_hour = _frames()
    entry.iloc[60, entry.columns.get_loc('High')] = 106.0

    events = build_key_level_event_dataset(entry, hour, four_hour, timeframe='5m')
    event_time = entry.index[60] + pd.Timedelta(minutes=5)

    assert event_time not in events.index


def test_factor_summary_groups_known_features_and_marks_small_samples() -> None:
    events = pd.DataFrame(
        {
            'side': ['BUY', 'BUY', 'SELL', 'SELL', 'BUY', 'SELL'],
            'filter_4h': ['FILTER_LONG', 'FILTER_LONG', 'FILTER_SHORT', 'FILTER_SHORT', 'FILTER_LONG', 'FILTER_SHORT'],
            'volume_ratio': [0.5, 0.8, 1.0, 1.4, 1.8, 2.4],
            'atr_pct': [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
            'forward_return_1h': [0.01, -0.01, 0.02, -0.02, 0.01, 0.03],
            'forward_return_1h_net': [0.0086, -0.0114, 0.0186, -0.0214, 0.0086, 0.0286],
        }
    )

    summary = summarize_one_hour_factor_buckets(events)

    assert set(summary['factor']) == {
        'direction',
        'filter_4h',
        'volume_tertile',
        'volatility_tertile',
    }
    assert summary['meets_minimum_sample'].eq(False).all()
    assert {'samples', 'average_gross_return', 'average_net_return', 'win_rate_pct'} <= set(summary.columns)
