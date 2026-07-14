from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.audit_order_flow_data import (
    ArchiveAuditRow,
    CoverageAuditRow,
    reconcile_agg_trades_and_klines,
    write_audit_report,
)
from src.data.order_flow import AggTradeAudit


def test_report_shows_integrity_coverage_and_no_strategy(tmp_path) -> None:
    audit = AggTradeAudit(
        symbol='BTCUSDT',
        day='2024-01-01',
        raw_rows=100,
        duplicate_trade_ids=0,
        invalid_rows=0,
        out_of_day_rows=0,
        populated_five_minute_buckets=288,
        missing_five_minute_buckets=0,
        maximum_volume_conservation_error=0.0,
        first_timestamp=pd.Timestamp('2024-01-01T00:00:00Z'),
        last_timestamp=pd.Timestamp('2024-01-01T23:55:00Z'),
        status='PASS',
    )
    sample = ArchiveAuditRow(
        symbol='BTCUSDT',
        dataset='aggTrades',
        period='2024-01-01',
        archive_path=Path('sample.zip'),
        archive_bytes=1024,
        rows=100,
        columns=('agg_trade_id', 'price'),
        checksum_verified=True,
        agg_trade_audit=audit,
    )
    coverage = CoverageAuditRow(
        symbol='BTCUSDT',
        dataset='aggTrades',
        first_period='2024-01-01',
        first_bytes=1024,
        last_period='2025-12-31',
        last_bytes=2048,
    )
    output = tmp_path / 'audit.md'

    write_audit_report([sample], [coverage], output)

    report = output.read_text(encoding='utf-8')
    assert '- Sample checksums passed: `yes`.' in report
    assert '- aggTrades normalization passed: `yes`.' in report
    assert '- Required archive boundary coverage passed: `yes`.' in report
    assert '- Strategy generated: `no`.' in report


def test_reconciliation_proves_enhanced_kline_taker_volume_matches_trades(
    tmp_path,
) -> None:
    index = pd.date_range('2024-01-01', periods=288, freq='5min', tz='UTC')
    agg_path = tmp_path / 'agg.csv'
    kline_path = tmp_path / 'kline.csv'
    pd.DataFrame(
        {
            'base_volume': 10.0,
            'taker_buy_base_volume': 6.0,
        },
        index=index,
    ).to_csv(agg_path, index_label='timestamp')
    pd.DataFrame(
        {
            'volume': 10.0,
            'taker_buy_volume': 6.0,
        },
        index=index,
    ).to_csv(kline_path, index_label='timestamp')
    rows = [
        ArchiveAuditRow(
            symbol='BTCUSDT',
            dataset='aggTrades',
            period='2024-01-01',
            archive_path=Path('agg.zip'),
            archive_bytes=1,
            rows=1,
            columns=(),
            checksum_verified=True,
            normalized_path=agg_path,
        ),
        ArchiveAuditRow(
            symbol='BTCUSDT',
            dataset='klines_5m',
            period='2024-01-01',
            archive_path=Path('kline.zip'),
            archive_bytes=1,
            rows=1,
            columns=(),
            checksum_verified=True,
            normalized_path=kline_path,
        ),
    ]

    result = reconcile_agg_trades_and_klines(rows)

    assert len(result) == 1
    assert result[0].matched_timestamps == 288
    assert result[0].status == 'PASS'
