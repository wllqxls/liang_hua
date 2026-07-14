from __future__ import annotations

import pandas as pd
import pytest

from src.research.event_factors import FIXED_ROUND_TRIP_COST
from src.research.order_flow_fading_push import (
    EVENT_COOLDOWN_BARS,
    build_fading_push_events,
    summarize_fading_push_events,
)


def _frame() -> pd.DataFrame:
    index = pd.date_range('2024-01-01', periods=70, freq='15min', tz='UTC')
    return pd.DataFrame(
        {
            'open': 100.0,
            'high': 100.5,
            'low': 99.5,
            'close': 100.0,
            'volume': 100.0,
            'taker_buy_volume': 50.0,
            'sum_open_interest': 1_000.0,
            'metrics_available': True,
        },
        index=index,
    )


def _add_fading_push(frame: pd.DataFrame, position: int, *, close: float = 99.8, oi: float = 1_003.0) -> None:
    frame.iloc[position, frame.columns.get_loc('close')] = close
    frame.iloc[position, frame.columns.get_loc('taker_buy_volume')] = 55.0
    frame.iloc[position, frame.columns.get_loc('sum_open_interest')] = oi


def test_event_uses_same_closed_bar_and_adds_future_sell_labels() -> None:
    frame = _frame()
    _add_fading_push(frame, 30)
    frame.iloc[32, frame.columns.get_loc('close')] = 98.0

    events, eligible_rows, excluded_metric_rows = build_fading_push_events(frame)

    row = events.loc[frame.index[30]]
    assert eligible_rows == 1
    assert excluded_metric_rows == 0
    assert row['side'] == 'SELL'
    assert row['taker_buy_ratio'] == pytest.approx(0.55)
    assert row['forward_return_30m'] == pytest.approx(99.8 / 98.0 - 1.0)
    assert row['forward_return_30m_net'] == pytest.approx(99.8 / 98.0 - 1.0 - FIXED_ROUND_TRIP_COST)


def test_oi_gap_in_the_four_bar_feature_window_excludes_event() -> None:
    frame = _frame()
    _add_fading_push(frame, 30)
    frame.iloc[27, frame.columns.get_loc('metrics_available')] = False
    frame.iloc[27, frame.columns.get_loc('sum_open_interest')] = float('nan')

    events, eligible_rows, excluded_metric_rows = build_fading_push_events(frame)

    assert events.empty
    assert eligible_rows == 0
    assert excluded_metric_rows >= 1


def test_cooldown_removes_overlapping_candidates() -> None:
    frame = _frame()
    first = 30
    second = first + EVENT_COOLDOWN_BARS - 1
    third = first + EVENT_COOLDOWN_BARS
    _add_fading_push(frame, first, close=99.8, oi=1_003.0)
    _add_fading_push(frame, second, close=99.7, oi=1_006.0)
    _add_fading_push(frame, third, close=99.6, oi=1_003.0)

    events, eligible_rows, _ = build_fading_push_events(frame)

    assert eligible_rows == 3
    assert list(events.index) == [frame.index[first], frame.index[third]]


def test_summary_marks_insufficient_buckets_as_descriptive() -> None:
    frame = _frame()
    _add_fading_push(frame, 30)
    events, _, _ = build_fading_push_events(frame)

    summary = summarize_fading_push_events(events)

    overall = summary.loc[
        (summary['horizon'] == '30m') & (summary['factor'] == 'overall') & (summary['bucket'] == 'ALL')
    ].iloc[0]
    assert int(overall['samples']) == 1
    assert bool(overall['meets_minimum_sample']) is False
