from __future__ import annotations

import pandas as pd
import pytest

from src.research.event_factors import FIXED_ROUND_TRIP_COST
from src.research.order_flow_failed_push import (
    EVENT_COOLDOWN_BARS,
    aggregate_order_flow_to_15m,
    build_failed_push_reversal_events,
    summarize_failed_push_events,
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


def _add_failed_push(frame: pd.DataFrame, position: int) -> None:
    frame.iloc[position, frame.columns.get_loc('open')] = 100.0
    frame.iloc[position, frame.columns.get_loc('high')] = 101.0
    frame.iloc[position, frame.columns.get_loc('low')] = 99.0
    frame.iloc[position, frame.columns.get_loc('close')] = 99.8
    frame.iloc[position, frame.columns.get_loc('volume')] = 200.0
    frame.iloc[position, frame.columns.get_loc('taker_buy_volume')] = 130.0
    frame.iloc[position, frame.columns.get_loc('sum_open_interest')] = 1_003.0


def test_aggregates_three_complete_five_minute_bars() -> None:
    index = pd.date_range('2024-01-01', periods=3, freq='5min', tz='UTC')
    frame = pd.DataFrame(
        {
            'open': [100.0, 101.0, 102.0],
            'high': [102.0, 103.0, 104.0],
            'low': [99.0, 100.0, 101.0],
            'close': [101.0, 102.0, 103.0],
            'volume': [10.0, 20.0, 30.0],
            'taker_buy_volume': [6.0, 12.0, 18.0],
            'sum_open_interest': [1_000.0, 1_001.0, 1_002.0],
            'metrics_available': [True, True, True],
        },
        index=index,
    )

    result = aggregate_order_flow_to_15m(frame)

    row = result.iloc[0]
    assert row['open'] == 100.0
    assert row['high'] == 104.0
    assert row['low'] == 99.0
    assert row['close'] == 103.0
    assert row['volume'] == 60.0
    assert row['taker_buy_volume'] == 36.0
    assert row['sum_open_interest'] == 1_002.0
    assert bool(row['metrics_available']) is True


def test_failed_push_event_has_only_future_sell_labels() -> None:
    frame = _frame()
    _add_failed_push(frame, 30)
    frame.iloc[32, frame.columns.get_loc('close')] = 98.0

    events, eligible_rows, excluded_metric_rows = build_failed_push_reversal_events(frame)

    row = events.loc[frame.index[30]]
    assert eligible_rows == 1
    assert excluded_metric_rows == 0
    assert row['side'] == 'SELL'
    assert row['taker_buy_ratio'] == pytest.approx(0.65)
    assert row['forward_return_30m'] == pytest.approx(99.8 / 98.0 - 1.0)
    assert row['forward_return_30m_net'] == pytest.approx(
        99.8 / 98.0 - 1.0 - FIXED_ROUND_TRIP_COST
    )


def test_metric_gap_excludes_event_without_oi_fill() -> None:
    frame = _frame()
    _add_failed_push(frame, 30)
    frame.iloc[20, frame.columns.get_loc('metrics_available')] = False
    frame.iloc[20, frame.columns.get_loc('sum_open_interest')] = float('nan')

    events, eligible_rows, excluded_metric_rows = build_failed_push_reversal_events(frame)

    assert events.empty
    assert eligible_rows == 0
    assert excluded_metric_rows >= 1


def test_frozen_cooldown_removes_overlapping_candidates() -> None:
    frame = _frame()
    first = 30
    second = first + EVENT_COOLDOWN_BARS - 1
    third = first + EVENT_COOLDOWN_BARS
    for position in (first, second, third):
        _add_failed_push(frame, position)
    frame.iloc[second, frame.columns.get_loc('sum_open_interest')] = 1_006.0

    events, eligible_rows, _ = build_failed_push_reversal_events(frame)

    assert eligible_rows == 3
    assert list(events.index) == [frame.index[first], frame.index[third]]


def test_summary_marks_small_buckets_as_descriptive() -> None:
    frame = _frame()
    _add_failed_push(frame, 30)
    events, _, _ = build_failed_push_reversal_events(frame)

    summary = summarize_failed_push_events(events)

    overall = summary.loc[
        (summary['horizon'] == '30m')
        & (summary['factor'] == 'overall')
        & (summary['bucket'] == 'ALL')
    ].iloc[0]
    assert int(overall['samples']) == 1
    assert bool(overall['meets_minimum_sample']) is False
