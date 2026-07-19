from __future__ import annotations

import pandas as pd
import pytest

import src.backtest.semi_auto_optimizer as optimizer
from src.backtest.semi_auto_optimizer import (
    DESIGN_YEAR,
    HOLDING_WINDOWS,
    OI_CHANGE_THRESHOLDS,
    TAKER_BUY_RATIO_THRESHOLDS,
    _candidate_metrics,
    _sample_score,
    build_semi_auto_whitelist,
    write_semi_auto_whitelist,
)
from src.research.event_factors import FIXED_ROUND_TRIP_COST


def test_empty_whitelist_csv_keeps_order_flow_schema(tmp_path) -> None:
    destination = tmp_path / 'whitelist.csv'

    write_semi_auto_whitelist([], destination)

    frame = pd.read_csv(destination)
    assert frame.empty
    assert {
        'rank', 'symbol', 'design_year', 'taker_buy_ratio_threshold',
        'oi_change_45m_threshold', 'holding_window', 'events',
        'average_gross_return', 'average_round_trip_cost',
        'average_funding_return', 'average_net_return', 'trigger_logic',
    } <= set(frame.columns)


def test_candidate_metrics_use_next_open_fixed_exit_cost_and_real_short_funding() -> None:
    fifteen_index = pd.date_range('2024-01-01', periods=4, freq='15min', tz='UTC')
    fifteen_minute = pd.DataFrame(
        {
            'open': [110.0, 100.0, 99.0, 98.0],
            'high': [111.0, 101.0, 100.0, 99.0],
            'low': [109.0, 99.0, 97.0, 97.0],
            'close': [110.0, 99.0, 98.0, 98.0],
        },
        index=fifteen_index,
    )
    five_index = pd.date_range('2024-01-01', periods=9, freq='5min', tz='UTC')
    five_minute = pd.DataFrame({'close': [100.0] * 6 + [99.0, 99.0, 98.0]}, index=five_index)
    funding_rates = pd.Series(
        [0.005, 0.001],
        index=pd.DatetimeIndex(['2024-01-01 00:15:00+00:00', '2024-01-01 00:30:00+00:00']),
    )
    events = pd.DataFrame(
        {
            'open': [111.0], 'high': [112.0], 'low': [109.0], 'close': [110.0],
            'atr_pct': [2.0 / 110.0],
        },
        index=fifteen_index[:1],
    )

    metrics = _candidate_metrics(
        fifteen_minute=fifteen_minute,
        five_minute=five_minute,
        funding_rates=funding_rates,
        events=events,
        holding_bars=2,
    )

    expected_gross = (100.0 - 98.0) / 100.0
    expected_funding = 0.001 * 100.0 / 100.0
    assert metrics['events'] == 1
    assert metrics['average_gross_return'] == pytest.approx(expected_gross)
    assert metrics['average_funding_return'] == pytest.approx(expected_funding)
    assert metrics['average_net_return'] == pytest.approx(
        expected_gross - FIXED_ROUND_TRIP_COST + expected_funding,
    )
    assert metrics['visual_score'] == pytest.approx(0.5)


@pytest.mark.parametrize(('events', 'expected'), [(30, 0.0), (65, 1.0), (100, 0.0)])
def test_sample_score_peaks_at_65_events(events: int, expected: float) -> None:
    assert _sample_score(events) == pytest.approx(expected)


def test_search_grid_is_frozen_at_27_combinations() -> None:
    assert len(TAKER_BUY_RATIO_THRESHOLDS) * len(OI_CHANGE_THRESHOLDS) * len(HOLDING_WINDOWS) == 27


def test_whitelist_loader_reads_only_2024(monkeypatch, tmp_path) -> None:
    years: list[int] = []
    index = pd.date_range('2024-01-01', periods=12, freq='5min', tz='UTC')
    five_minute = pd.DataFrame(
        {
            'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.0,
            'volume': 10.0, 'taker_buy_volume': 6.0, 'sum_open_interest': 1000.0,
            'metrics_available': True,
        },
        index=index,
    )

    def fake_order_flow(root, *, symbol, year):
        years.append(year)
        return five_minute

    def fake_funding(root, *, symbol, year):
        years.append(year)
        return pd.Series([0.0001], index=pd.DatetimeIndex(['2024-01-01 00:00:00+00:00']))

    monkeypatch.setattr(optimizer, 'load_order_flow_year', fake_order_flow)
    monkeypatch.setattr(optimizer, 'load_funding_year', fake_funding)
    monkeypatch.setattr(optimizer, 'build_fading_push_candidates', lambda *args, **kwargs: (pd.DataFrame(), 0, 0))

    assert build_semi_auto_whitelist(tmp_path, symbol='BTC/USDT') == []
    assert years == [DESIGN_YEAR, DESIGN_YEAR]
