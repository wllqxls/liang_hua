from __future__ import annotations

import pandas as pd
import pytest

from src.research.momentum_reversion_events import (
    FIXED_ROUND_TRIP_COST,
    build_momentum_reversion_event_study,
    summarize_momentum_reversion_buckets,
)


def _five_minute_frame() -> pd.DataFrame:
    index = pd.date_range('2026-01-01', periods=130, freq='5min', tz='UTC')
    close = pd.Series(100.0, index=index)
    close.iloc[60] = 105.0
    close.iloc[61] = 110.0
    close.iloc[62] = 100.0
    close.iloc[73] = 95.0
    close.iloc[74] = 90.0
    close.iloc[75] = 100.0
    return pd.DataFrame(
        {
            'Open': close.shift(1).fillna(100.0),
            'High': close + 0.5,
            'Low': close - 0.5,
            'Close': close,
            'Volume': 100.0,
        },
        index=index,
    )


def test_extreme_episode_creates_one_a_and_next_bar_mean_reversion_b() -> None:
    five_minute = _five_minute_frame()

    study = build_momentum_reversion_event_study(five_minute)

    sell_events = study.event_a.loc[study.event_a['side'] == 'SELL']
    assert len(sell_events) == 1
    event_time = five_minute.index[61] + pd.Timedelta(minutes=5)
    row = study.event_a.loc[event_time]
    assert bool(row['converted_next_bar']) is True
    assert row['forward_return_1h'] == pytest.approx(95.0 / 110.0 * -1 + 1)
    assert row['forward_return_1h_net'] == pytest.approx(
        95.0 / 110.0 * -1 + 1 - FIXED_ROUND_TRIP_COST
    )
    assert study.event_b.loc[study.event_b['source_event_time'] == event_time].shape[0] == 1


def test_future_prices_only_change_labels_not_a_features() -> None:
    five_minute = _five_minute_frame()
    changed = five_minute.copy()
    changed.iloc[73, changed.columns.get_loc('Close')] = 90.0
    changed.iloc[73, changed.columns.get_loc('High')] = 90.5
    changed.iloc[73, changed.columns.get_loc('Low')] = 89.5

    base = build_momentum_reversion_event_study(five_minute)
    changed_study = build_momentum_reversion_event_study(changed)
    event_time = five_minute.index[61] + pd.Timedelta(minutes=5)
    feature_columns = ['side', 'rsi', 'rsi_extremity', 'band_excess_ratio']

    assert base.event_a.loc[event_time, feature_columns].to_dict() == (
        changed_study.event_a.loc[event_time, feature_columns].to_dict()
    )
    assert base.event_a.loc[event_time, 'forward_return_1h'] != (
        changed_study.event_a.loc[event_time, 'forward_return_1h']
    )


def test_summary_has_profit_factor_and_minimum_sample_gate() -> None:
    events = pd.DataFrame(
        {
            'side': ['BUY', 'BUY', 'SELL', 'SELL', 'BUY', 'SELL'],
            'rsi_extremity': [1, 2, 3, 4, 5, 6],
            'band_excess_ratio': [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
            'forward_return_1h': [0.01, -0.01, 0.02, -0.02, 0.01, 0.03],
            'forward_return_1h_net': [0.0086, -0.0114, 0.0186, -0.0214, 0.0086, 0.0286],
        }
    )

    summary = summarize_momentum_reversion_buckets(events)

    assert set(summary['factor']) == {
        'direction',
        'rsi_extremity_tertile',
        'band_excess_tertile',
    }
    buy_row = summary.loc[
        (summary['factor'] == 'direction') & (summary['bucket'] == 'BUY')
    ].iloc[0]
    assert buy_row['profit_factor'] == pytest.approx(0.0172 / 0.0114)
    assert bool(buy_row['meets_minimum_sample']) is False
