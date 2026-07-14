from __future__ import annotations

from typing import Any

import pandas as pd

from src.data import order_flow_yearly as yearly


def test_annual_archive_plan_uses_small_public_datasets_only() -> None:
    tasks = yearly.annual_archive_tasks(2024)

    assert len(tasks) == 2 * (366 + 12 + 12)
    assert {item.dataset for item in tasks} == {'klines_5m', 'metrics', 'fundingRate'}
    assert {item.symbol for item in tasks} == {'BTCUSDT', 'ETHUSDT'}
    assert not any(item.dataset in {'aggTrades', 'bookDepth'} for item in tasks)


def test_fetch_year_reports_archive_progress_and_builds_both_symbols(
    monkeypatch: Any,
    tmp_path,
) -> None:
    downloaded: list[yearly.AnnualArchiveTask] = []
    built: list[str] = []
    progress: list[dict[str, object]] = []

    monkeypatch.setattr(
        yearly,
        '_download_task',
        lambda root, task: downloaded.append(task) or root / task.period,
    )
    monkeypatch.setattr(
        yearly,
        '_build_symbol_year',
        lambda *, root, symbol, year: built.append(symbol),
    )
    monkeypatch.setattr(
        yearly,
        'inspect_order_flow_year',
        lambda *, root, year: [],
    )

    result = yearly.fetch_order_flow_year(
        year=2025,
        root=tmp_path,
        progress=lambda **values: progress.append(values),
        max_workers=4,
    )

    assert result == []
    assert len(downloaded) == 2 * (365 + 12 + 12)
    assert built == ['BTCUSDT', 'ETHUSDT']
    assert progress[0] == {'stage': '下载官方归档', 'completed': 0, 'total': len(downloaded)}
    assert any(item['completed'] == len(downloaded) for item in progress)


def test_inspect_year_distinguishes_missing_and_complete(tmp_path) -> None:
    missing = yearly.inspect_order_flow_year(root=tmp_path, year=2024)
    assert [item.state for item in missing] == ['missing', 'missing']

    index = pd.date_range(
        '2024-01-01', '2025-01-01', freq='5min', inclusive='left', tz='UTC'
    )
    funding_index = pd.date_range(
        '2024-01-01', '2025-01-01', freq='8h', inclusive='left', tz='UTC'
    )
    for symbol in yearly.SUPPORTED_SYMBOLS:
        data_path = yearly.annual_order_flow_path(tmp_path, symbol=symbol, year=2024)
        funding_path = yearly.annual_funding_path(tmp_path, symbol=symbol, year=2024)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        funding_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            'timestamp': index,
            'symbol': symbol,
            'close': 1.0,
            'volume': 1.0,
            'taker_buy_volume': 0.6,
            'taker_sell_volume': 0.4,
            'order_flow_imbalance': 0.2,
            'sum_open_interest': 1.0,
        }).to_csv(data_path, index=False)
        pd.DataFrame({
            'timestamp': funding_index,
            'symbol': symbol,
            'last_funding_rate': 0.0,
        }).to_csv(
            funding_path, index=False
        )

    complete = yearly.inspect_order_flow_year(root=tmp_path, year=2024)
    assert [item.state for item in complete] == ['complete', 'complete']
    assert all(item.rows == 105_408 and item.missing_rows == 0 for item in complete)


def test_holdout_year_can_be_inspected_but_not_downloaded(tmp_path) -> None:
    statuses = yearly.inspect_order_flow_year(root=tmp_path, year=2026)
    assert all(item.state == 'missing' for item in statuses)

    try:
        yearly.annual_archive_tasks(2026)
    except ValueError as exc:
        assert '保留期' in str(exc)
    else:
        raise AssertionError('2026 download must stay locked')
