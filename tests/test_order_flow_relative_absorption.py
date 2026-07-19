from __future__ import annotations

import pandas as pd
import pytest

from src.research.order_flow_relative_absorption import build_relative_absorption_candidates


def _frame() -> pd.DataFrame:
    index = pd.date_range('2024-01-01', periods=45, freq='15min', tz='UTC')
    oi = [1_000.0 * (1.001 ** position) for position in range(len(index))]
    return pd.DataFrame({
        'open': 100.0,
        'high': 100.5,
        'low': 99.5,
        'close': 100.0,
        'volume': 100.0,
        'taker_buy_volume': 51.0,
        'sum_open_interest': oi,
        'metrics_available': True,
    }, index=index)


def _event(frame: pd.DataFrame, position: int) -> None:
    frame.iloc[position, frame.columns.get_loc('taker_buy_volume')] = 80.0
    frame.iloc[position, frame.columns.get_loc('sum_open_interest')] *= 1.02
    frame.iloc[position, frame.columns.get_loc('close')] = 99.0


def test_relative_absorption_uses_prior_only_thresholds() -> None:
    frame = _frame()
    _event(frame, 25)

    before, _, _ = build_relative_absorption_candidates(
        frame, rolling_window_bars=20, event_cooldown_bars=1,
    )
    original_threshold = before.loc[frame.index[25], 'taker_ratio_threshold']
    frame.iloc[30:, frame.columns.get_loc('taker_buy_volume')] = 99.0
    after, _, _ = build_relative_absorption_candidates(
        frame, rolling_window_bars=20, event_cooldown_bars=1,
    )

    assert frame.index[25] in after.index
    assert after.loc[frame.index[25], 'taker_ratio_threshold'] == pytest.approx(original_threshold)
    assert original_threshold == pytest.approx(.51)


def test_relative_absorption_requires_weak_close_and_positive_oi() -> None:
    frame = _frame()
    _event(frame, 25)
    _event(frame, 30)
    frame.iloc[30, frame.columns.get_loc('close')] = 101.0

    events, qualified, excluded = build_relative_absorption_candidates(
        frame, rolling_window_bars=20, event_cooldown_bars=1,
    )

    assert frame.index[25] in events.index
    assert frame.index[30] not in events.index
    assert qualified >= 1
    assert excluded == 0
    assert events.iloc[0]['side'] == 'SELL'
    assert events.iloc[0]['factor_id'] == 'RELATIVE_ABSORPTION_V1'


def test_relative_absorption_applies_four_bar_cooldown() -> None:
    frame = _frame()
    _event(frame, 25)
    _event(frame, 27)
    _event(frame, 29)

    events, qualified, _ = build_relative_absorption_candidates(
        frame, rolling_window_bars=20,
    )

    assert qualified == 3
    assert list(events.index) == [frame.index[25], frame.index[29]]
