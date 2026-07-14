"""Download one public order-flow sample day and write a quality audit."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.order_flow import (
    ORDER_FLOW_ROOT,
    AggTradeAudit,
    FuturesKlineArchiveSpec,
    KlineOrderFlowAudit,
    MetricsAudit,
    PublicArchiveSpec,
    download_public_archive,
    download_public_kline_archive,
    normalize_agg_trades_archive,
    normalize_futures_kline_archive,
    normalize_metrics_archive,
    parse_checksum,
    public_archive_size,
    public_kline_archive_size,
    read_archive_csv,
    sha256_file,
)


logger = logging.getLogger(__name__)
SYMBOLS = ('BTCUSDT', 'ETHUSDT')
SAMPLE_DATASETS = ('aggTrades', 'metrics', 'fundingRate', 'bookDepth')
AUDITED_AGG_TRADE_HISTORY_BYTES = int(28.04 * 1024 * 1024 * 1024)


@dataclass(frozen=True, slots=True)
class ArchiveAuditRow:
    symbol: str
    dataset: str
    period: str
    archive_path: Path
    archive_bytes: int
    rows: int
    columns: tuple[str, ...]
    checksum_verified: bool
    normalized_path: Path | None = None
    agg_trade_audit: AggTradeAudit | None = None
    metrics_audit: MetricsAudit | None = None
    kline_audit: KlineOrderFlowAudit | None = None


@dataclass(frozen=True, slots=True)
class CoverageAuditRow:
    symbol: str
    dataset: str
    first_period: str
    first_bytes: int | None
    last_period: str
    last_bytes: int | None


@dataclass(frozen=True, slots=True)
class CrossSourceAuditRow:
    symbol: str
    matched_timestamps: int
    missing_timestamps: int
    maximum_total_base_relative_error: float
    maximum_taker_buy_base_relative_error: float
    daily_total_base_relative_error: float
    daily_taker_buy_base_relative_error: float
    status: str


def run_sample_audit(
    *,
    data_root: Path = PROJECT_ROOT / ORDER_FLOW_ROOT,
    day: str = '2024-01-01',
    symbols: Sequence[str] = SYMBOLS,
) -> tuple[list[ArchiveAuditRow], list[CoverageAuditRow]]:
    """Download bounded samples, verify checksums, and inspect schemas."""
    month = day[:7]
    sample_rows: list[ArchiveAuditRow] = []
    for symbol in symbols:
        kline_spec = FuturesKlineArchiveSpec(symbol, day)
        logger.info('downloading dataset=klines_5m symbol=%s period=%s', symbol, day)
        kline_archive = download_public_kline_archive(data_root, kline_spec)
        kline_checksum_path = kline_archive.with_name(
            f'{kline_archive.name}.CHECKSUM'
        )
        kline_checksum_verified = sha256_file(kline_archive) == parse_checksum(
            kline_checksum_path.read_text(encoding='utf-8')
        )
        kline_normalized_path, kline_audit = normalize_futures_kline_archive(
            kline_archive,
            symbol=symbol,
            day=day,
            output_root=data_root,
        )
        kline_frame = read_archive_csv(kline_archive)
        sample_rows.append(
            ArchiveAuditRow(
                symbol=symbol,
                dataset='klines_5m',
                period=day,
                archive_path=kline_archive,
                archive_bytes=kline_archive.stat().st_size,
                rows=len(kline_frame),
                columns=tuple(str(column) for column in kline_frame.columns),
                checksum_verified=kline_checksum_verified,
                normalized_path=kline_normalized_path,
                kline_audit=kline_audit,
            )
        )
        for dataset in SAMPLE_DATASETS:
            period = month if dataset == 'fundingRate' else day
            spec = PublicArchiveSpec(dataset, symbol, period)
            logger.info('downloading dataset=%s symbol=%s period=%s', dataset, symbol, period)
            archive = download_public_archive(data_root, spec)
            checksum_path = archive.with_name(f'{archive.name}.CHECKSUM')
            checksum_verified = sha256_file(archive) == parse_checksum(
                checksum_path.read_text(encoding='utf-8')
            )
            normalized_path: Path | None = None
            agg_trade_audit: AggTradeAudit | None = None
            metrics_audit: MetricsAudit | None = None
            if dataset == 'aggTrades':
                normalized_path, agg_trade_audit = normalize_agg_trades_archive(
                    archive,
                    symbol=symbol,
                    day=day,
                    output_root=data_root,
                )
                rows = agg_trade_audit.raw_rows
                columns = (
                    'agg_trade_id',
                    'price',
                    'quantity',
                    'first_trade_id',
                    'last_trade_id',
                    'transact_time',
                    'is_buyer_maker',
                )
            elif dataset == 'metrics':
                normalized_path, metrics_audit = normalize_metrics_archive(
                    archive,
                    symbol=symbol,
                    day=day,
                    output_root=data_root,
                )
                frame = read_archive_csv(archive)
                rows = len(frame)
                columns = tuple(str(column) for column in frame.columns)
            else:
                frame = read_archive_csv(archive)
                rows = len(frame)
                columns = tuple(str(column) for column in frame.columns)
            sample_rows.append(
                ArchiveAuditRow(
                    symbol=symbol,
                    dataset=dataset,
                    period=period,
                    archive_path=archive,
                    archive_bytes=archive.stat().st_size,
                    rows=rows,
                    columns=columns,
                    checksum_verified=checksum_verified,
                    normalized_path=normalized_path,
                    agg_trade_audit=agg_trade_audit,
                    metrics_audit=metrics_audit,
                )
            )
    return sample_rows, audit_target_coverage(symbols=symbols)


def audit_target_coverage(
    *,
    symbols: Sequence[str] = SYMBOLS,
) -> list[CoverageAuditRow]:
    """Check first and last target archives without downloading their bodies."""
    rows: list[CoverageAuditRow] = []
    for symbol in symbols:
        first_kline = FuturesKlineArchiveSpec(symbol, '2024-01-01')
        last_kline = FuturesKlineArchiveSpec(symbol, '2025-12-31')
        rows.append(
            CoverageAuditRow(
                symbol=symbol,
                dataset='klines_5m',
                first_period=first_kline.day,
                first_bytes=public_kline_archive_size(first_kline),
                last_period=last_kline.day,
                last_bytes=public_kline_archive_size(last_kline),
            )
        )
        for dataset in SAMPLE_DATASETS:
            first_period = '2024-01' if dataset == 'fundingRate' else '2024-01-01'
            last_period = '2025-12' if dataset == 'fundingRate' else '2025-12-31'
            first = PublicArchiveSpec(dataset, symbol, first_period)
            last = PublicArchiveSpec(dataset, symbol, last_period)
            rows.append(
                CoverageAuditRow(
                    symbol=symbol,
                    dataset=dataset,
                    first_period=first_period,
                    first_bytes=public_archive_size(first),
                    last_period=last_period,
                    last_bytes=public_archive_size(last),
                )
            )
    return rows


def write_audit_report(
    sample_rows: Sequence[ArchiveAuditRow],
    coverage_rows: Sequence[CoverageAuditRow],
    output_path: Path,
    *,
    estimated_agg_trade_history_bytes: int | None = None,
    cross_source_rows: Sequence[CrossSourceAuditRow] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    checksums_pass = all(row.checksum_verified for row in sample_rows)
    agg_audits = [row.agg_trade_audit for row in sample_rows if row.agg_trade_audit]
    agg_pass = bool(agg_audits) and all(audit.status == 'PASS' for audit in agg_audits)
    metrics_audits = [row.metrics_audit for row in sample_rows if row.metrics_audit]
    metrics_pass = bool(metrics_audits) and all(
        audit.status == 'PASS' for audit in metrics_audits
    )
    kline_audits = [row.kline_audit for row in sample_rows if row.kline_audit]
    kline_pass = bool(kline_audits) and all(
        audit.status == 'PASS' for audit in kline_audits
    )
    cross_rows = list(cross_source_rows or [])
    cross_source_pass = bool(cross_rows) and all(
        row.status == 'PASS' for row in cross_rows
    )
    coverage_pass = all(
        row.first_bytes is not None and row.last_bytes is not None
        for row in coverage_rows
    )
    lines = [
        '# Order-Flow Public Data Quality Audit',
        '',
        '- Scope: data availability and integrity only; no factor or strategy is generated.',
        '- Source: Binance Data Collection, USDⓈ-M Futures public archives.',
        '- Sample: BTCUSDT and ETHUSDT on UTC 2024-01-01; funding uses 2024-01 monthly archive.',
        '- Full-history bodies were not downloaded; target coverage uses HTTP HEAD on 2024 start and 2025 end archives.',
        f'- Estimated BTC/ETH 2024–2025 monthly aggTrades download: `{estimated_agg_trade_history_bytes / 1024 / 1024 / 1024:.2f} GB compressed`.' if estimated_agg_trade_history_bytes is not None else '- Full aggTrades size estimate: `not calculated`.',
        '- Design: `docs/research/order-flow-data-design.md`.',
        f'- Code revision: `{_git_revision()}`.',
        '',
        '## Downloaded sample archives',
        '',
        '| Symbol | Dataset | Period | Compressed MB | Rows | SHA-256 verified | Columns |',
        '|---|---|---|---:|---:|---|---|',
    ]
    for row in sample_rows:
        lines.append(
            f'| {row.symbol} | {row.dataset} | {row.period} | '
            f'{row.archive_bytes / 1024 / 1024:.2f} | {row.rows} | '
            f'{"yes" if row.checksum_verified else "no"} | '
            f'{", ".join(row.columns)} |'
        )
    lines.extend(
        [
            '',
            '## aggTrades 5m normalization',
            '',
            '| Symbol | Raw rows | Duplicate IDs | Invalid rows | Out-of-day rows | Populated 5m buckets | Missing buckets | Volume conservation max error | Status |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---|',
        ]
    )
    for audit in agg_audits:
        lines.append(
            f'| {audit.symbol} | {audit.raw_rows} | {audit.duplicate_trade_ids} | '
            f'{audit.invalid_rows} | {audit.out_of_day_rows} | '
            f'{audit.populated_five_minute_buckets} | {audit.missing_five_minute_buckets} | '
            f'{audit.maximum_volume_conservation_error:.12g} | {audit.status} |'
        )
    lines.extend(
        [
            '',
            '## metrics 5m alignment',
            '',
            '| Symbol | Rows | Duplicate timestamps | Invalid rows | Out-of-day rows | Missing 5m timestamps | Status |',
            '|---|---:|---:|---:|---:|---:|---|',
        ]
    )
    for audit in metrics_audits:
        lines.append(
            f'| {audit.symbol} | {audit.rows} | {audit.duplicate_timestamps} | '
            f'{audit.invalid_rows} | {audit.out_of_day_rows} | '
            f'{audit.missing_five_minute_timestamps} | {audit.status} |'
        )
    lines.extend(
        [
            '',
            '## Enhanced 5m kline order flow',
            '',
            '| Symbol | Rows | Duplicate timestamps | Invalid rows | Out-of-day rows | Missing 5m timestamps | Base conservation error | Quote conservation error | Status |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---|',
        ]
    )
    for audit in kline_audits:
        lines.append(
            f'| {audit.symbol} | {audit.rows} | {audit.duplicate_timestamps} | '
            f'{audit.invalid_rows} | {audit.out_of_day_rows} | '
            f'{audit.missing_five_minute_timestamps} | '
            f'{audit.maximum_base_volume_error:.12g} | '
            f'{audit.maximum_quote_volume_error:.12g} | {audit.status} |'
        )
    lines.extend(
        [
            '',
            '## aggTrades ↔ enhanced kline reconciliation',
            '',
            '- An aggTrade represents one aggregated taker order and can straddle a 5m boundary. Per-bucket differences are diagnostic; the gate uses full-day volume conservation.',
            '',
            '| Symbol | Matched 5m timestamps | Missing timestamps | Max bucket total error | Max bucket taker-buy error | Daily total error | Daily taker-buy error | Status |',
            '|---|---:|---:|---:|---:|---:|---:|---|',
        ]
    )
    for row in cross_rows:
        lines.append(
            f'| {row.symbol} | {row.matched_timestamps} | {row.missing_timestamps} | '
            f'{row.maximum_total_base_relative_error:.12g} | '
            f'{row.maximum_taker_buy_base_relative_error:.12g} | '
            f'{row.daily_total_base_relative_error:.12g} | '
            f'{row.daily_taker_buy_base_relative_error:.12g} | {row.status} |'
        )
    lines.extend(
        [
            '',
            '## Target-period boundary coverage',
            '',
            '| Symbol | Dataset | First target | Available | Last target | Available |',
            '|---|---|---|---|---|---|',
        ]
    )
    for row in coverage_rows:
        lines.append(
            f'| {row.symbol} | {row.dataset} | {row.first_period} | '
            f'{"yes" if row.first_bytes is not None else "no"} | '
            f'{row.last_period} | {"yes" if row.last_bytes is not None else "no"} |'
        )
    lines.extend(
        [
            '',
            '## Gate',
            '',
            f'- Sample checksums passed: `{"yes" if checksums_pass else "no"}`.',
            f'- aggTrades normalization passed: `{"yes" if agg_pass else "no"}`.',
            f'- OI metrics 5m alignment passed: `{"yes" if metrics_pass else "no"}`.',
            f'- Enhanced 5m kline order-flow fields passed: `{"yes" if kline_pass else "no"}`.',
            f'- aggTrades versus enhanced kline reconciliation passed: `{"yes" if cross_source_pass else "no"}`.',
            f'- Required archive boundary coverage passed: `{"yes" if coverage_pass else "no"}`.',
            '- Historical liquidation archive: `not confirmed`; no liquidation field may be fabricated.',
            '- Strategy generated: `no`.',
            '',
        ]
    )
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def reconcile_agg_trades_and_klines(
    sample_rows: Sequence[ArchiveAuditRow],
) -> list[CrossSourceAuditRow]:
    """Prove enhanced kline taker fields match independently aggregated trades."""
    rows: list[CrossSourceAuditRow] = []
    for symbol in SYMBOLS:
        agg_row = next(
            (
                row
                for row in sample_rows
                if row.symbol == symbol and row.dataset == 'aggTrades'
            ),
            None,
        )
        kline_row = next(
            (
                row
                for row in sample_rows
                if row.symbol == symbol and row.dataset == 'klines_5m'
            ),
            None,
        )
        if (
            agg_row is None
            or kline_row is None
            or agg_row.normalized_path is None
            or kline_row.normalized_path is None
        ):
            continue
        agg = pd.read_csv(agg_row.normalized_path, index_col='timestamp', parse_dates=True)
        kline = pd.read_csv(kline_row.normalized_path, index_col='timestamp', parse_dates=True)
        aligned = agg.join(kline, how='inner', lsuffix='_agg', rsuffix='_kline')
        missing_timestamps = len(agg.index.union(kline.index)) - len(aligned)
        total_error = _maximum_relative_error(
            aligned['base_volume'],
            aligned['volume'],
        )
        buy_error = _maximum_relative_error(
            aligned['taker_buy_base_volume'],
            aligned['taker_buy_volume'],
        )
        daily_total_error = _relative_error_of_sums(
            aligned['base_volume'],
            aligned['volume'],
        )
        daily_buy_error = _relative_error_of_sums(
            aligned['taker_buy_base_volume'],
            aligned['taker_buy_volume'],
        )
        status = 'PASS'
        if (
            len(aligned) != 288
            or missing_timestamps
            or daily_total_error > 1e-4
            or daily_buy_error > 1e-4
        ):
            status = 'FAIL'
        rows.append(
            CrossSourceAuditRow(
                symbol=symbol,
                matched_timestamps=len(aligned),
                missing_timestamps=missing_timestamps,
                maximum_total_base_relative_error=total_error,
                maximum_taker_buy_base_relative_error=buy_error,
                daily_total_base_relative_error=daily_total_error,
                daily_taker_buy_base_relative_error=daily_buy_error,
                status=status,
            )
        )
    return rows


def _maximum_relative_error(left: pd.Series, right: pd.Series) -> float:
    denominator = right.abs().clip(lower=1.0)
    return float(((left - right).abs() / denominator).max())


def _relative_error_of_sums(left: pd.Series, right: pd.Series) -> float:
    denominator = max(abs(float(right.sum())), 1.0)
    return abs(float(left.sum()) - float(right.sum())) / denominator


def _git_revision() -> str:
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return 'unavailable'
    return result.stdout.strip() or 'unavailable'


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Audit public order-flow sample data.')
    parser.add_argument('--day', default='2024-01-01')
    parser.add_argument(
        '--output',
        type=Path,
        default=PROJECT_ROOT / 'docs' / 'research' / 'order-flow-data-audit.md',
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = _parse_args()
    sample_rows, coverage_rows = run_sample_audit(day=args.day)
    cross_source_rows = reconcile_agg_trades_and_klines(sample_rows)
    write_audit_report(
        sample_rows,
        coverage_rows,
        args.output,
        estimated_agg_trade_history_bytes=AUDITED_AGG_TRADE_HISTORY_BYTES,
        cross_source_rows=cross_source_rows,
    )
    logger.info('sample_rows=%s coverage_rows=%s output=%s', len(sample_rows), len(coverage_rows), args.output)


if __name__ == '__main__':
    main()
