from __future__ import annotations

import pandas as pd
import pytest

from src.research.event_factors import FIXED_ROUND_TRIP_COST
from src.research.order_flow_events import (
    EVENT_COOLDOWN_BARS,
    build_order_flow_impulse_events,
    summarize_order_flow_events,
)


def _frame() -> pd.DataFrame:
    index = pd.date_range('2024-01-01', periods=90, freq='5min', tz='UTC')
    return pd.DataFrame(
        {
            'close': 100.0,
            'volume': 100.0,
            'order_flow_imbalance': 0.0,
            'sum_open_interest': 1_000.0,
            'metrics_available': True,
        },
        index=index,
    )


def _add_buy_impulse(frame: pd.DataFrame, position: int) -> None:
    frame.iloc[position, frame.columns.get_loc('close')] = 100.2
    frame.iloc[position, frame.columns.get_loc('volume')] = 200.0
    frame.iloc[position, frame.columns.get_loc('order_flow_imbalance')] = 0.4
    frame.iloc[position, frame.columns.get_loc('sum_open_interest')] = 1_003.0


def test_event_uses_closed_features_and_adds_future_labels() -> None:
    frame = _frame()
    _add_buy_impulse(frame, 40)
    frame.iloc[43, frame.columns.get_loc('close')] = 101.0

    events, eligible_rows, excluded_metric_rows = build_order_flow_impulse_events(frame)

    row = events.loc[frame.index[40]]
    assert eligible_rows == 1
    assert excluded_metric_rows == 0
    assert row['side'] == 'BUY'
    assert row['volume_ratio'] == pytest.approx(2.0)
    assert row['oi_change_15m'] == pytest.approx(0.003)
    assert row['forward_return_15m'] == pytest.approx(101.0 / 100.2 - 1.0)
    assert row['forward_return_15m_net'] == pytest.approx(
        101.0 / 100.2 - 1.0 - FIXED_ROUND_TRIP_COST
    )


def test_metric_gap_in_feature_window_excludes_candidate_without_filling_oi() -> None:
    frame = _frame()
    _add_buy_impulse(frame, 50)
    frame.iloc[40, frame.columns.get_loc('metrics_available')] = False
    frame.iloc[40, frame.columns.get_loc('sum_open_interest')] = float('nan')

    events, eligible_rows, excluded_metric_rows = build_order_flow_impulse_events(frame)

    assert events.empty
    assert eligible_rows == 0
    assert excluded_metric_rows >= 1


def test_events_use_the_frozen_twelve_bar_cooldown() -> None:
    frame = _frame()
    first_position = 35
    second_position = first_position + EVENT_COOLDOWN_BARS - 1
    third_position = first_position + EVENT_COOLDOWN_BARS
    for position in (first_position, second_position, third_position):
        _add_buy_impulse(frame, position)

    events, eligible_rows, _ = build_order_flow_impulse_events(frame)

    assert eligible_rows == 3
    assert list(events.index) == [frame.index[first_position], frame.index[third_position]]


def test_summary_keeps_small_buckets_descriptive_only() -> None:
    frame = _frame()
    _add_buy_impulse(frame, 40)
    events, _, _ = build_order_flow_impulse_events(frame)

    summary = summarize_order_flow_events(events)

    overall = summary.loc[
        (summary['horizon'] == '15m')
        & (summary['factor'] == 'overall')
        & (summary['bucket'] == 'ALL')
    ].iloc[0]
    assert int(overall['samples']) == 1
    assert bool(overall['meets_minimum_sample']) is False
