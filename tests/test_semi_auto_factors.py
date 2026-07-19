from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest import semi_auto_factors as factors


def test_catalog_builds_exactly_btc_and_eth_with_three_years(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(factors, 'load_order_flow_year', lambda *args, **kwargs: pd.DataFrame({'x': [1]}))
    monkeypatch.setattr(factors, 'load_funding_year', lambda *args, **kwargs: pd.Series([0.0]))
    monkeypatch.setattr(factors, 'aggregate_order_flow_to_15m', lambda frame: frame)
    monkeypatch.setattr(factors, 'build_relative_absorption_candidates', lambda *args, **kwargs: (pd.DataFrame(), 0, 0))
    monkeypatch.setattr(factors, '_candidate_metrics', lambda **kwargs: {
        'events': 40, 'net_wins': 21, 'net_losses': 19,
        'average_gross_return': .002, 'average_funding_return': .00001,
        'average_net_return': .00061, 'median_net_return': .0004,
        'profit_factor': 1.1,
    })

    items = factors.build_semi_auto_factors(tmp_path)

    assert [item.symbol for item in items] == ['BTC/USDT', 'ETH/USDT']
    assert [item.metrics_2023.year for item in items] == [2023, 2023]
    assert all(item.metrics_2024.samples == 40 for item in items)
    assert all(item.metrics_2025.average_round_trip_cost == .0014 for item in items)


def test_catalog_csv_allows_each_generated_symbol_as_experimental_strategy(tmp_path) -> None:
    metric = factors.AnnualFactorMetrics(2023, 3, 2, 1, .001, .0014, 0, -.0004, -.0003, .8)
    items = [factors.SemiAutoFactorItem(
        symbol=symbol, factor_id='RELATIVE_ABSORPTION_V1',
        mode='ORDER_FLOW_ABSORPTION_15M', timeframe='15m', holding_window='4h',
        rolling_window_bars=2880, relative_quantile=.8, trigger_logic='fixture',
        metrics_2023=metric, metrics_2024=metric, metrics_2025=metric,
    ) for symbol in ('BTC/USDT', 'ETH/USDT')]
    destination = tmp_path / 'factors.csv'

    factors.write_semi_auto_factors(items, destination)

    assert factors.is_persisted_experimental_factor(
        destination, symbol='BTC/USDT', factor_id='RELATIVE_ABSORPTION_V1', holding_window='4h',
    )
    assert factors.is_persisted_experimental_factor(
        destination, symbol='ETH/USDT', factor_id='RELATIVE_ABSORPTION_V1', holding_window='4h',
    )
    assert not factors.is_persisted_experimental_factor(
        destination, symbol='SOL/USDT', factor_id='RELATIVE_ABSORPTION_V1', holding_window='4h',
    )
