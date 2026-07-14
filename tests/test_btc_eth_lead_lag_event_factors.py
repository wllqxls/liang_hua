from __future__ import annotations

import pandas as pd
import pytest

from src.research.event_factors import (
    FIXED_ROUND_TRIP_COST,
    build_btc_eth_lead_lag_dataset,
    summarize_btc_eth_lead_lag,
)


def _frame(close: pd.Series) -> pd.DataFrame:
    open_price = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([open_price, close], axis=1).max(axis=1) + 0.2
    low = pd.concat([open_price, close], axis=1).min(axis=1) - 0.2
    return pd.DataFrame(
        {
            'Open': open_price,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': 100.0,
        },
        index=close.index,
    )


def _lead_lag_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range('2025-01-01', periods=100, freq='5min', tz='UTC')
    btc_close = pd.Series(100.0, index=index)
    eth_close = pd.Series(100.0, index=index)
    btc_close.iloc[41:44] = [100.1, 100.3, 101.0]
    eth_close.iloc[41:44] = [100.02, 100.05, 100.20]
    eth_close.iloc[44] = 100.40
    eth_close.iloc[45] = 100.60
    eth_close.iloc[46] = 100.80
    eth_close.iloc[47:50] = [100.85, 100.90, 101.00]
    eth_close.iloc[50:56] = [101.05, 101.08, 101.10, 101.12, 101.15, 101.20]
    return _frame(btc_close), _frame(eth_close)


def test_btc_impulse_and_eth_lag_create_eth_directional_event() -> None:
    btc, eth = _lead_lag_frames()

    events = build_btc_eth_lead_lag_dataset(btc, eth)

    event_time = btc.index[43] + pd.Timedelta(minutes=5)
    row = events.loc[event_time]
    assert row['side'] == 'BUY'
    assert row['btc_displacement_atr'] >= 1.0
    assert 0 <= row['eth_displacement_atr'] <= row['btc_displacement_atr'] * 0.5
    expected_gross = 100.80 / 100.20 - 1
    assert row['forward_return_15m'] == pytest.approx(expected_gross)
    assert row['forward_return_15m_net'] == pytest.approx(
        expected_gross - FIXED_ROUND_TRIP_COST
    )


def test_future_eth_price_changes_labels_not_event_features() -> None:
    btc, eth = _lead_lag_frames()
    changed = eth.copy()
    changed.iloc[46, changed.columns.get_loc('Close')] = 99.0

    base = build_btc_eth_lead_lag_dataset(btc, eth)
    changed_events = build_btc_eth_lead_lag_dataset(btc, changed)
    event_time = btc.index[43] + pd.Timedelta(minutes=5)
    feature_columns = [
        'side',
        'btc_close',
        'eth_close',
        'btc_displacement_atr',
        'eth_displacement_atr',
        'lag_ratio',
    ]

    assert base.loc[event_time, feature_columns].to_dict() == (
        changed_events.loc[event_time, feature_columns].to_dict()
    )
    assert base.loc[event_time, 'forward_return_15m'] != changed_events.loc[
        event_time,
        'forward_return_15m',
    ]


def test_summary_includes_break_even_cost_and_daily_block_interval() -> None:
    index = pd.DatetimeIndex(
        ['2025-01-01T01:00:00Z', '2025-01-02T01:00:00Z']
    )
    data: dict[str, list[float]] = {}
    for horizon in ('5m', '15m', '30m', '1h'):
        data[f'forward_return_{horizon}'] = [0.002, 0.002]
        data[f'forward_return_{horizon}_net'] = [0.0006, 0.0006]
    events = pd.DataFrame(data, index=index)

    summary = summarize_btc_eth_lead_lag(events)

    primary = summary.loc[summary['horizon'] == '15m'].iloc[0]
    assert primary['samples'] == 2
    assert primary['break_even_round_trip_cost'] == pytest.approx(0.002)
    assert primary['average_net_return'] == pytest.approx(0.0006)
    assert primary['net_mean_ci_lower'] == pytest.approx(0.0006)
    assert primary['net_mean_ci_upper'] == pytest.approx(0.0006)
    assert pd.isna(primary['profit_factor'])
