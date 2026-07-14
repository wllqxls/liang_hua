from __future__ import annotations

import pandas as pd
import pytest

from src.research.event_factors import (
    FIXED_ROUND_TRIP_COST,
    build_volume_absorption_event_study,
    summarize_absorption_reversal_buckets,
)


def _entry_frame() -> pd.DataFrame:
    index = pd.date_range('2025-01-01', periods=130, freq='5min', tz='UTC')
    close = pd.Series(100.0, index=index)
    close.iloc[58] = 101.5
    close.iloc[59] = 102.3
    close.iloc[60] = 102.5
    close.iloc[61] = 102.2
    close.iloc[62] = 101.7
    high = close + 0.5
    low = close - 0.5
    high.iloc[60] = 102.7
    low.iloc[60] = 102.3
    volume = pd.Series(100.0, index=index)
    volume.iloc[60] = 400.0
    return pd.DataFrame(
        {
            'Open': close.shift(1).fillna(100.0),
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': volume,
        },
        index=index,
    )


def test_absorption_a_matches_one_reversal_b_and_adds_costed_labels() -> None:
    entry = _entry_frame()

    study = build_volume_absorption_event_study(entry, timeframe='5m')

    event_time = entry.index[60] + pd.Timedelta(minutes=5)
    row = study.event_a.loc[event_time]
    assert len(study.event_a) == 1
    assert row['side'] == 'SELL'
    assert row['volume_ratio'] == pytest.approx(4.0)
    assert row['range_atr'] <= 0.8
    assert row['displacement_atr'] >= 1.0
    assert bool(row['converted_to_b']) is True
    assert row['bars_to_b'] == 2
    expected_gross = -(100.0 / 102.5 - 1)
    assert row['forward_return_1h'] == pytest.approx(expected_gross)
    assert row['forward_return_1h_net'] == pytest.approx(
        expected_gross - FIXED_ROUND_TRIP_COST
    )
    assert len(study.event_b) == 1


def test_future_price_changes_only_change_labels_not_event_features() -> None:
    entry = _entry_frame()
    changed = entry.copy()
    changed.iloc[72, changed.columns.get_loc('Close')] = 99.0
    changed.iloc[72, changed.columns.get_loc('High')] = 100.5
    changed.iloc[72, changed.columns.get_loc('Low')] = 98.5

    base = build_volume_absorption_event_study(entry, timeframe='5m')
    changed_study = build_volume_absorption_event_study(changed, timeframe='5m')
    event_time = entry.index[60] + pd.Timedelta(minutes=5)
    feature_columns = [
        'side',
        'volume_ratio',
        'range_atr',
        'displacement_atr',
        'atr',
    ]

    assert base.event_a.loc[event_time, feature_columns].to_dict() == (
        changed_study.event_a.loc[event_time, feature_columns].to_dict()
    )
    assert base.event_a.loc[event_time, 'forward_return_1h'] != (
        changed_study.event_a.loc[event_time, 'forward_return_1h']
    )


def test_absorption_summary_has_overall_profit_factor_and_sample_gate() -> None:
    events = pd.DataFrame(
        {
            'side': ['BUY', 'BUY', 'SELL', 'SELL'],
            'volume_ratio': [3.1, 3.5, 4.0, 5.0],
            'absorption_strength': [0.2, 0.3, 0.4, 0.5],
            'forward_return_1h': [0.01, -0.01, 0.02, -0.02],
            'forward_return_1h_net': [0.0086, -0.0114, 0.0186, -0.0214],
        }
    )

    summary = summarize_absorption_reversal_buckets(events)

    overall = summary.loc[summary['factor'] == 'overall'].iloc[0]
    assert overall['bucket'] == 'ALL'
    assert overall['profit_factor'] == pytest.approx(0.0272 / 0.0328)
    assert bool(overall['meets_minimum_sample']) is False
