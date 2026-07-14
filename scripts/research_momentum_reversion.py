"""Generate read-only extreme-momentum mean-reversion factor reports."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import validate_strategies
from scripts.research_event_factors import _calendar_year_slice, _covers_calendar_year
from src.backtest.engine import BacktestEngine
from src.research.momentum_reversion_events import (
    FIXED_ROUND_TRIP_COST,
    MomentumReversionEventStudy,
    build_momentum_reversion_event_study,
    summarize_momentum_reversion_buckets,
)


logger = logging.getLogger(__name__)
SYMBOLS = ('BTC/USDT', 'ETH/USDT')
YEARS = (2024, 2025, 2026)
MINIMUM_EVENT_SAMPLES = 200
MINIMUM_CONVERSION_RATE = 0.10
HORIZONS = ('5m', '15m', '1h', '4h')


@dataclass(frozen=True, slots=True)
class HorizonMetrics:
    average_gross_return: float
    average_net_return: float
    win_rate_pct: float
    profit_factor: float


@dataclass(frozen=True, slots=True)
class MomentumReversionResearchSlice:
    symbol: str
    year: int
    status: str
    verdict: str
    reasons: tuple[str, ...]
    event_a_count: int
    event_b_count: int
    conversion_rate: float
    event_a_dataset_path: Path | None
    event_b_dataset_path: Path | None
    horizon_metrics: dict[str, HorizonMetrics]
    summary: pd.DataFrame
    error: str | None = None


def run_momentum_reversion_research(
    *,
    data_root: Path = PROJECT_ROOT / 'data',
    output_root: Path = PROJECT_ROOT / 'results' / 'research',
    symbols: Sequence[str] = SYMBOLS,
    years: Sequence[int] = YEARS,
) -> list[MomentumReversionResearchSlice]:
    """Build each symbol's study once, then report true UTC calendar slices."""
    slices: list[MomentumReversionResearchSlice] = []
    for symbol in symbols:
        try:
            five_minute = _load_five_minute_data(data_root, symbol=symbol)
            study = build_momentum_reversion_event_study(five_minute)
        except (FileNotFoundError, ValueError) as exc:
            slices.extend(_unavailable_slice(symbol, year, str(exc)) for year in years)
            continue
        for year in years:
            slices.append(
                _slice_study(
                    study=study,
                    five_minute=five_minute,
                    output_root=output_root,
                    symbol=symbol,
                    year=year,
                )
            )
    return slices


def write_momentum_reversion_report(
    slices: Sequence[MomentumReversionResearchSlice],
    output_path: Path,
) -> None:
    """Write a report that enforces the no-strategy rejection gates."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Extreme-Momentum Mean-Reversion Event Factor Report',
        '',
        '- Scope: read-only event research; this report creates no strategy or trade.',
        f'- Fixed round-trip cost: `{FIXED_ROUND_TRIP_COST:.4f}`.',
        '- Event A is scored in its contrarian direction: upper extreme = SELL, lower extreme = BUY.',
        '- Event B only measures whether the immediately next 5m close returned past the then-known Bollinger middle band.',
        '- Hard rejection: any slice with A→B conversion below 10% or fewer than 200 A events cannot become a strategy.',
        '- Design: `docs/research/momentum-reversion-design.md`.',
        f'- Code revision: `{_git_revision()}`.',
        '',
    ]
    for item in slices:
        lines.extend(
            [
                f'## {item.symbol} / 5m / {item.year}',
                '',
                f'- Status: `{item.status}`',
                f'- Decision: `{item.verdict}`',
                f'- Event A (extreme momentum): `{item.event_a_count}`',
                f'- Event B (next-bar middle-band reversion): `{item.event_b_count}`',
                f'- A→B conversion: `{item.conversion_rate * 100:.2f}%`',
            ]
        )
        for reason in item.reasons:
            lines.append(f'- Rejection reason: {reason}')
        if item.event_a_dataset_path is not None:
            lines.append(f'- A dataset: `{item.event_a_dataset_path.as_posix()}`')
        if item.event_b_dataset_path is not None:
            lines.append(f'- B dataset: `{item.event_b_dataset_path.as_posix()}`')
        if item.error is not None:
            lines.append(f'- Data note: {item.error}')
        if not item.horizon_metrics:
            lines.extend(['', 'No post-event labels available.', ''])
            continue
        lines.extend(
            [
                '',
                '| A holding period | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor |',
                '|---|---:|---:|---:|---:|',
            ]
        )
        for horizon in HORIZONS:
            metric = item.horizon_metrics.get(horizon)
            if metric is None:
                continue
            lines.append(
                f'| {horizon} | {metric.average_gross_return * 100:.4f} | '
                f'{metric.average_net_return * 100:.4f} | {metric.win_rate_pct:.2f} | '
                f'{_format_profit_factor(metric.profit_factor)} |'
            )
        if item.summary.empty:
            lines.extend(['', 'No one-hour A buckets available.', ''])
            continue
        lines.extend(
            [
                '',
                '| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Net Profit Factor | Meets 200-sample rule |',
                '|---|---|---:|---:|---:|---:|---:|---|',
            ]
        )
        for row in item.summary.itertuples(index=False):
            lines.append(
                '| '
                f'{row.factor} | {row.bucket} | {row.samples} | '
                f'{row.average_gross_return * 100:.4f} | '
                f'{row.average_net_return * 100:.4f} | '
                f'{row.win_rate_pct:.2f} | {_format_profit_factor(row.profit_factor)} | '
                f'{"yes" if row.meets_minimum_sample else "no"} |'
            )
        lines.append('')
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def _load_five_minute_data(data_root: Path, *, symbol: str) -> pd.DataFrame:
    safe_symbol = symbol.replace('/', '_')
    sources = validate_strategies._data_sources(data_root, safe_symbol, '5m')
    if not sources:
        raise FileNotFoundError(f'{symbol} missing data sources: 5m')
    has_yearly_sources = any(source.parent != data_root for source in sources)
    if has_yearly_sources:
        merged_dir = PROJECT_ROOT / 'tmp' / 'research_data' / safe_symbol
        merged_dir.mkdir(parents=True, exist_ok=True)
        merged = validate_strategies._merge_data_sources(sources)
        path = merged_dir / f'{safe_symbol}_5m.csv'
        merged.to_csv(path)
    else:
        path = data_root / f'{safe_symbol}_5m.csv'
    return BacktestEngine(data_dir=path.parent).load_data(path)


def _slice_study(
    *,
    study: MomentumReversionEventStudy,
    five_minute: pd.DataFrame,
    output_root: Path,
    symbol: str,
    year: int,
) -> MomentumReversionResearchSlice:
    safe_symbol = symbol.replace('/', '_')
    event_a = _calendar_year_slice(study.event_a, year=year)
    event_b = _calendar_year_slice(study.event_b, year=year)
    if event_a.empty:
        return _unavailable_slice(
            symbol,
            year,
            'merged data has no extreme-momentum A events in the requested calendar year',
        )
    output_root.mkdir(parents=True, exist_ok=True)
    event_a_path = output_root / f'{safe_symbol}_5m_{year}_momentum_reversion_a.csv'
    event_b_path = output_root / f'{safe_symbol}_5m_{year}_momentum_reversion_b.csv'
    event_a.to_csv(event_a_path)
    event_b.to_csv(event_b_path)
    conversion_rate = float(event_a['converted_next_bar'].mean())
    verdict, reasons = _research_verdict(
        samples=len(event_a),
        conversion_rate=conversion_rate,
    )
    status = 'COMPLETE_YEAR' if _covers_calendar_year(five_minute, year=year) else 'PARTIAL_YEAR'
    return MomentumReversionResearchSlice(
        symbol=symbol,
        year=year,
        status=status,
        verdict=verdict,
        reasons=reasons,
        event_a_count=len(event_a),
        event_b_count=len(event_b),
        conversion_rate=conversion_rate,
        event_a_dataset_path=event_a_path,
        event_b_dataset_path=event_b_path,
        horizon_metrics=_horizon_metrics(event_a),
        summary=summarize_momentum_reversion_buckets(event_a),
    )


def _research_verdict(*, samples: int, conversion_rate: float) -> tuple[str, tuple[str, ...]]:
    reasons: list[str] = []
    if samples < MINIMUM_EVENT_SAMPLES:
        reasons.append(f'A samples {samples} < {MINIMUM_EVENT_SAMPLES}')
    if conversion_rate < MINIMUM_CONVERSION_RATE:
        reasons.append(f'A→B conversion {conversion_rate * 100:.2f}% < 10%')
    return (
        ('REJECT_NO_STRATEGY', tuple(reasons))
        if reasons
        else ('RESEARCH_ONLY_NOT_A_STRATEGY', tuple())
    )


def _horizon_metrics(events: pd.DataFrame) -> dict[str, HorizonMetrics]:
    result: dict[str, HorizonMetrics] = {}
    for horizon in HORIZONS:
        gross_column = f'forward_return_{horizon}'
        net_column = f'forward_return_{horizon}_net'
        usable = events.dropna(subset=[gross_column, net_column])
        if usable.empty:
            continue
        net_returns = usable[net_column]
        losses = -net_returns[net_returns < 0].sum()
        profits = net_returns[net_returns > 0].sum()
        result[horizon] = HorizonMetrics(
            average_gross_return=float(usable[gross_column].mean()),
            average_net_return=float(net_returns.mean()),
            win_rate_pct=float((net_returns > 0).mean() * 100),
            profit_factor=float('nan') if losses == 0 else float(profits / losses),
        )
    return result


def _format_profit_factor(value: float) -> str:
    return 'N/A' if not np.isfinite(value) else f'{value:.3f}'


def _unavailable_slice(
    symbol: str,
    year: int,
    error: str,
) -> MomentumReversionResearchSlice:
    return MomentumReversionResearchSlice(
        symbol=symbol,
        year=year,
        status='DATA_UNAVAILABLE',
        verdict='REJECT_NO_STRATEGY',
        reasons=(error,),
        event_a_count=0,
        event_b_count=0,
        conversion_rate=0.0,
        event_a_dataset_path=None,
        event_b_dataset_path=None,
        horizon_metrics={},
        summary=pd.DataFrame(),
        error=error,
    )


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
    parser = argparse.ArgumentParser(
        description='Generate extreme-momentum mean-reversion factor research.'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=PROJECT_ROOT / 'docs' / 'research' / 'momentum-reversion-report.md',
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = _parse_args()
    slices = run_momentum_reversion_research()
    write_momentum_reversion_report(slices, args.output)
    logger.info('slices=%s output=%s', len(slices), args.output)


if __name__ == '__main__':
    main()
