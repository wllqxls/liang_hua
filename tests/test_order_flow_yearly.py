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
    funding_timestamps = funding_index.astype(str).tolist()
    funding_timestamps[10] = '2024-01-04 08:00:00.001+00:00'
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
            'metrics_available': True,
        }).to_csv(data_path, index=False)
        pd.DataFrame({
            'timestamp': funding_timestamps,
            'symbol': symbol,
            'last_funding_rate': 0.0,
        }).to_csv(
            funding_path, index=False
        )

    complete = yearly.inspect_order_flow_year(root=tmp_path, year=2024)
    assert [item.state for item in complete] == ['complete', 'complete']
    assert all(item.rows == 105_408 and item.missing_rows == 0 for item in complete)
    assert all(item.metrics_missing_rows == 0 for item in complete)
    assert all(item.metrics_coverage_pct == 100.0 for item in complete)

    btc_path = yearly.annual_order_flow_path(tmp_path, symbol='BTCUSDT', year=2024)
    btc = pd.read_csv(btc_path)
    btc.loc[100:101, 'metrics_available'] = False
    btc.loc[100:101, 'sum_open_interest'] = float('nan')
    btc.to_csv(btc_path, index=False)
    audited = yearly.inspect_order_flow_year(root=tmp_path, year=2024)
    assert audited[0].state == 'usable'
    assert audited[0].metrics_missing_rows == 2
    assert audited[0].metrics_coverage_pct > 99.0
    assert audited[1].state == 'complete'


def test_annual_metrics_keep_real_gaps_without_fabricating_values() -> None:
    index = pd.date_range(
        '2024-01-01', '2025-01-01', freq='5min', inclusive='left', tz='UTC'
    )
    available = index.delete([100, 101])
    timestamps = available.astype(str).to_series(index=range(len(available)))
    timestamps.iloc[10] = '2024-01-01 00:50:03+00:00'
    frame = pd.DataFrame({
        'create_time': timestamps,
        'symbol': 'BTCUSDT',
        'sum_open_interest': 100.0,
        'sum_open_interest_value': 1_000.0,
        'count_toptrader_long_short_ratio': 1.1,
        'sum_toptrader_long_short_ratio': 1.2,
        'count_long_short_ratio': 1.3,
        'sum_taker_long_short_vol_ratio': 1.4,
    })

    normalized, audit = yearly.normalize_annual_metrics(
        frame,
        symbol='BTCUSDT',
        year=2024,
    )

    assert len(normalized) == 105_408
    assert audit.missing_rows == 2
    assert audit.coverage_pct > 99.0
    assert normalized['metrics_available'].sum() == 105_406
    assert pd.isna(normalized.iloc[100]['sum_open_interest'])
    assert normalized.iloc[100]['metrics_available'] == False  # noqa: E712


def test_holdout_year_can_be_inspected_but_not_downloaded(tmp_path) -> None:
    statuses = yearly.inspect_order_flow_year(root=tmp_path, year=2026)
    assert all(item.state == 'missing' for item in statuses)

    try:
        yearly.annual_archive_tasks(2026)
    except ValueError as exc:
        assert '保留期' in str(exc)
    else:
        raise AssertionError('2026 download must stay locked')
