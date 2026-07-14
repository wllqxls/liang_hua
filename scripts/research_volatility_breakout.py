"""Generate read-only volatility-compression breakout factor reports."""

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
from src.research.volatility_breakout_events import (
    FIXED_ROUND_TRIP_COST,
    VolatilityBreakoutEventStudy,
    build_volatility_breakout_event_study,
    summarize_breakout_buckets,
)


logger = logging.getLogger(__name__)
SYMBOLS = ('BTC/USDT', 'ETH/USDT')
YEARS = (2025, 2026)


@dataclass(frozen=True, slots=True)
class VolatilityBreakoutResearchSlice:
    symbol: str
    year: int
    status: str
    compression_events: int
    breakout_events: int
    conversion_rate: float
    compression_dataset_path: Path | None
    breakout_dataset_path: Path | None
    one_hour_metrics: 'BreakoutMetrics | None'
    summary: pd.DataFrame
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BreakoutMetrics:
    average_gross_return: float
    average_net_return: float
    win_rate_pct: float
    profit_factor: float


def run_volatility_breakout_research(
    *,
    data_root: Path = PROJECT_ROOT / 'data',
    output_root: Path = PROJECT_ROOT / 'results' / 'research',
    symbols: Sequence[str] = SYMBOLS,
    years: Sequence[int] = YEARS,
) -> list[VolatilityBreakoutResearchSlice]:
    """Build independent A/B event studies for each requested calendar year."""
    slices: list[VolatilityBreakoutResearchSlice] = []
    for symbol in symbols:
        for year in years:
            slices.append(
                _run_slice(
                    data_root=data_root,
                    output_root=output_root,
                    symbol=symbol,
                    year=year,
                )
            )
    return slices


def write_volatility_breakout_report(
    slices: Sequence[VolatilityBreakoutResearchSlice],
    output_path: Path,
) -> None:
    """Write the A/B event study report without deriving a trading strategy."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Volatility-Compression Breakout Event Factor Report',
        '',
        '- Scope: read-only A/B event research; this report creates no strategy or trade.',
        f'- Fixed round-trip cost: `{FIXED_ROUND_TRIP_COST:.4f}`.',
        '- Event A has no direction, so it reports sample count and A→B conversion only; return and Profit Factor apply to directional event B.',
        '- Buckets with fewer than 200 B events are descriptive only.',
        '- Design: `docs/research/volatility-breakout-design.md`.',
        f'- Code revision: `{_git_revision()}`.',
        '',
    ]
    for item in slices:
        lines.extend(
            [
                f'## {item.symbol} / 5m + 1h / {item.year}',
                '',
                f'- Status: `{item.status}`',
                f'- Event A (compression): `{item.compression_events}`',
                f'- Event B (first directional breakout after A): `{item.breakout_events}`',
                f'- A→B conversion: `{item.conversion_rate * 100:.2f}%`',
            ]
        )
        if item.compression_dataset_path is not None:
            lines.append(
                f'- A dataset: `{item.compression_dataset_path.as_posix()}`'
            )
        if item.breakout_dataset_path is not None:
            lines.append(f'- B dataset: `{item.breakout_dataset_path.as_posix()}`')
        if item.error is not None:
            lines.append(f'- Data note: {item.error}')
        if item.summary.empty:
            lines.extend(['', 'No one-hour directional B labels available.', ''])
            continue
        overall = item.one_hour_metrics
        if overall is None:
            lines.extend(['', 'No one-hour directional B labels available.', ''])
            continue
        lines.extend(
            [
                '',
                '| A→B one-hour metric | Value |',
                '|---|---:|',
                f'| Avg gross return % | {overall.average_gross_return * 100:.4f} |',
                f'| Avg net return % | {overall.average_net_return * 100:.4f} |',
                f'| Net win rate % | {overall.win_rate_pct:.2f} |',
                f'| Net Profit Factor | {_format_profit_factor(overall.profit_factor)} |',
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
                f'{row.win_rate_pct:.2f} | '
                f'{_format_profit_factor(row.profit_factor)} | '
                f'{"yes" if row.meets_minimum_sample else "no"} |'
            )
        lines.append('')
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def _run_slice(
    *,
    data_root: Path,
    output_root: Path,
    symbol: str,
    year: int,
) -> VolatilityBreakoutResearchSlice:
    safe_symbol = symbol.replace('/', '_')
    try:
        merged_dir = _materialize_research_data_dir(data_root, symbol=symbol)
        engine = BacktestEngine(data_dir=merged_dir)
        five_minute = engine.load_data(merged_dir / f'{safe_symbol}_5m.csv')
        one_hour = engine.load_data(merged_dir / f'{safe_symbol}_1h.csv')
        study = build_volatility_breakout_event_study(five_minute, one_hour)
        compression_events = _calendar_year_slice(study.compression_events, year=year)
        breakout_events = _calendar_year_slice(study.breakout_events, year=year)
        if compression_events.empty and breakout_events.empty:
            return _unavailable_slice(
                symbol,
                year,
                'merged data has no volatility-compression A or B events in the requested calendar year',
            )
        output_root.mkdir(parents=True, exist_ok=True)
        compression_path = output_root / f'{safe_symbol}_5m_{year}_volatility_compression_a.csv'
        breakout_path = output_root / f'{safe_symbol}_5m_{year}_volatility_breakout_b.csv'
        compression_events.to_csv(compression_path)
        breakout_events.to_csv(breakout_path)
        summary = summarize_breakout_buckets(breakout_events)
        status = (
            'COMPLETE_YEAR'
            if _covers_calendar_year(five_minute, year=year)
            and _covers_calendar_year(one_hour, year=year)
            else 'PARTIAL_YEAR'
        )
        return VolatilityBreakoutResearchSlice(
            symbol=symbol,
            year=year,
            status=status,
            compression_events=len(compression_events),
            breakout_events=len(breakout_events),
            conversion_rate=_conversion_rate(compression_events),
            compression_dataset_path=compression_path,
            breakout_dataset_path=breakout_path,
            one_hour_metrics=_overall_metrics(breakout_events),
            summary=summary,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _unavailable_slice(symbol, year, str(exc))


def _materialize_research_data_dir(data_root: Path, *, symbol: str) -> Path:
    safe_symbol = symbol.replace('/', '_')
    timeframes = ('5m', '1h')
    sources_by_timeframe = {
        timeframe: validate_strategies._data_sources(data_root, safe_symbol, timeframe)
        for timeframe in timeframes
    }
    if not all(sources_by_timeframe.values()):
        missing = [
            timeframe
            for timeframe, sources in sources_by_timeframe.items()
            if not sources
        ]
        raise FileNotFoundError(f'{symbol} missing data sources: {", ".join(missing)}')
    has_yearly_sources = any(
        source.parent != data_root
        for sources in sources_by_timeframe.values()
        for source in sources
    )
    if not has_yearly_sources:
        return data_root
    merged_dir = PROJECT_ROOT / 'tmp' / 'research_data' / safe_symbol
    merged_dir.mkdir(parents=True, exist_ok=True)
    for timeframe, sources in sources_by_timeframe.items():
        merged = validate_strategies._merge_data_sources(sources)
        merged.to_csv(merged_dir / f'{safe_symbol}_{timeframe}.csv')
    return merged_dir


def _conversion_rate(compression_events: pd.DataFrame) -> float:
    if compression_events.empty:
        return 0.0
    return float(compression_events['converted_to_breakout'].mean())


def _overall_metrics(events: pd.DataFrame) -> BreakoutMetrics | None:
    if events.empty:
        return None
    usable = events.dropna(subset=['forward_return_1h', 'forward_return_1h_net'])
    if usable.empty:
        return None
    net_returns = usable['forward_return_1h_net']
    losses = -net_returns[net_returns < 0].sum()
    profits = net_returns[net_returns > 0].sum()
    profit_factor = float('nan') if losses == 0 else float(profits / losses)
    return BreakoutMetrics(
        average_gross_return=float(usable['forward_return_1h'].mean()),
        average_net_return=float(net_returns.mean()),
        win_rate_pct=float((net_returns > 0).mean() * 100),
        profit_factor=profit_factor,
    )


def _format_profit_factor(value: float) -> str:
    return 'N/A' if not np.isfinite(value) else f'{value:.3f}'


def _unavailable_slice(
    symbol: str,
    year: int,
    error: str,
) -> VolatilityBreakoutResearchSlice:
    return VolatilityBreakoutResearchSlice(
        symbol=symbol,
        year=year,
        status='DATA_UNAVAILABLE',
        compression_events=0,
        breakout_events=0,
        conversion_rate=0.0,
        compression_dataset_path=None,
        breakout_dataset_path=None,
        one_hour_metrics=None,
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
        description='Generate volatility-compression breakout event factor research.'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=PROJECT_ROOT / 'docs' / 'research' / 'volatility-breakout-report.md',
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = _parse_args()
    slices = run_volatility_breakout_research()
    write_volatility_breakout_report(slices, args.output)
    logger.info('slices=%s output=%s', len(slices), args.output)


if __name__ == '__main__':
    main()
