from __future__ import annotations

import pandas as pd
import pytest

from src.research.event_factors import FIXED_ROUND_TRIP_COST
from src.research.order_flow_hourly_fading_push import (
    EVENT_COOLDOWN_BARS,
    aggregate_order_flow_to_1h,
    build_hourly_fading_push_events,
    summarize_hourly_fading_push_events,
)


def _hourly_frame() -> pd.DataFrame:
    index = pd.date_range('2024-01-01', periods=70, freq='1h', tz='UTC')
    return pd.DataFrame(
        {
            'open': 100.0, 'high': 100.5, 'low': 99.5, 'close': 100.0,
            'volume': 100.0, 'taker_buy_volume': 50.0,
            'sum_open_interest': 1_000.0, 'metrics_available': True,
        }, index=index,
    )


def _add_event(frame: pd.DataFrame, position: int, *, close: float = 99.8, oi: float = 1_003.0) -> None:
    frame.iloc[position, frame.columns.get_loc('close')] = close
    frame.iloc[position, frame.columns.get_loc('taker_buy_volume')] = 55.0
    frame.iloc[position, frame.columns.get_loc('sum_open_interest')] = oi


def test_aggregates_twelve_complete_five_minute_bars() -> None:
    index = pd.date_range('2024-01-01', periods=12, freq='5min', tz='UTC')
    frame = pd.DataFrame(
        {
            'open': range(100, 112), 'high': range(101, 113), 'low': range(99, 111),
            'close': range(100, 112), 'volume': 10.0, 'taker_buy_volume': 6.0,
            'sum_open_interest': range(1_000, 1_012), 'metrics_available': True,
        }, index=index,
    )

    result = aggregate_order_flow_to_1h(frame)

    row = result.iloc[0]
    assert row['open'] == 100.0
    assert row['high'] == 112.0
    assert row['low'] == 99.0
    assert row['close'] == 111.0
    assert row['volume'] == 120.0
    assert row['taker_buy_volume'] == 72.0
    assert row['sum_open_interest'] == 1_011.0
    assert bool(row['metrics_available']) is True


def test_hourly_event_has_post_event_sell_labels() -> None:
    frame = _hourly_frame()
    _add_event(frame, 30)
    frame.iloc[34, frame.columns.get_loc('close')] = 98.0

    events, eligible_rows, excluded_metric_rows = build_hourly_fading_push_events(frame)

    row = events.loc[frame.index[30]]
    assert eligible_rows == 1
    assert excluded_metric_rows == 0
    assert row['side'] == 'SELL'
    assert row['oi_change_3h'] == pytest.approx(0.003)
    assert row['forward_return_4h'] == pytest.approx(99.8 / 98.0 - 1.0)
    assert row['forward_return_4h_net'] == pytest.approx(99.8 / 98.0 - 1.0 - FIXED_ROUND_TRIP_COST)


def test_oi_gap_excludes_hourly_event_without_fill() -> None:
    frame = _hourly_frame()
    _add_event(frame, 30)
    frame.iloc[27, frame.columns.get_loc('metrics_available')] = False
    frame.iloc[27, frame.columns.get_loc('sum_open_interest')] = float('nan')

    events, eligible_rows, excluded_metric_rows = build_hourly_fading_push_events(frame)

    assert events.empty
    assert eligible_rows == 0
    assert excluded_metric_rows >= 1


def test_hourly_cooldown_removes_overlapping_candidates() -> None:
    frame = _hourly_frame()
    first = 30
    second = first + EVENT_COOLDOWN_BARS - 1
    third = first + EVENT_COOLDOWN_BARS
    _add_event(frame, first, close=99.8, oi=1_003.0)
    _add_event(frame, second, close=99.7, oi=1_006.0)
    _add_event(frame, third, close=99.6, oi=1_003.0)

    events, eligible_rows, _ = build_hourly_fading_push_events(frame)

    assert eligible_rows == 3
    assert list(events.index) == [frame.index[first], frame.index[third]]


def test_summary_marks_small_buckets_descriptive() -> None:
    frame = _hourly_frame()
    _add_event(frame, 30)
    events, _, _ = build_hourly_fading_push_events(frame)

    summary = summarize_hourly_fading_push_events(events)

    overall = summary.loc[
        (summary['horizon'] == '4h') & (summary['factor'] == 'overall') & (summary['bucket'] == 'ALL')
    ].iloc[0]
    assert int(overall['samples']) == 1
    assert bool(overall['meets_minimum_sample']) is False
