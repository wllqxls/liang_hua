"""Generate read-only key-level event factor datasets and reports."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import validate_strategies
from src.backtest.engine import BacktestEngine
from src.research.event_factors import (
    FIXED_ROUND_TRIP_COST,
    build_key_level_event_dataset,
    summarize_one_hour_factor_buckets,
)


logger = logging.getLogger(__name__)
SYMBOLS = ('BTC/USDT', 'ETH/USDT')
TIMEFRAMES = ('5m', '15m')
YEARS = (2025, 2026)


@dataclass(frozen=True, slots=True)
class FactorResearchSlice:
    symbol: str
    timeframe: str
    year: int
    status: str
    events: int
    dataset_path: Path | None
    summary: pd.DataFrame
    error: str | None = None


def run_event_factor_research(
    *,
    data_root: Path = PROJECT_ROOT / 'data',
    output_root: Path = PROJECT_ROOT / 'results' / 'research',
    symbols: Sequence[str] = SYMBOLS,
    timeframes: Sequence[str] = TIMEFRAMES,
    years: Sequence[int] = YEARS,
) -> list[FactorResearchSlice]:
    """Build event datasets for all available requested data slices."""
    slices: list[FactorResearchSlice] = []
    for symbol in symbols:
        for timeframe in timeframes:
            for year in years:
                slices.append(
                    _run_slice(
                        data_root=data_root,
                        output_root=output_root,
                        symbol=symbol,
                        timeframe=timeframe,
                        year=year,
                    )
                )
    return slices


def write_factor_report(
    slices: Sequence[FactorResearchSlice],
    output_path: Path,
) -> None:
    """Write the report without deriving a trading rule from its buckets."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Key-Level Event Factor Report',
        '',
        '- Scope: read-only event research; this report creates no strategy or trade.',
        f'- Fixed round-trip cost: `{FIXED_ROUND_TRIP_COST:.4f}`.',
        '- One-hour bucket results with fewer than 200 events are descriptive only.',
        '- Design: `docs/research/event-factor-design.md`.',
        '',
    ]
    for item in slices:
        lines.extend(
            [
                f'## {item.symbol} / {item.timeframe} / {item.year}',
                '',
                f'- Status: `{item.status}`',
                f'- Events: `{item.events}`',
            ]
        )
        if item.dataset_path is not None:
            lines.append(f'- Dataset: `{item.dataset_path.as_posix()}`')
        if item.error is not None:
            lines.append(f'- Data note: {item.error}')
        if item.summary.empty:
            lines.extend(['', 'No one-hour factor buckets available.', ''])
            continue
        lines.extend(
            [
                '',
                '| Factor | Bucket | Samples | Avg gross return % | Avg net return % | Net win rate % | Meets 200-sample rule |',
                '|---|---|---:|---:|---:|---:|---|',
            ]
        )
        for row in item.summary.itertuples(index=False):
            lines.append(
                '| '
                f'{row.factor} | {row.bucket} | {row.samples} | '
                f'{row.average_gross_return * 100:.4f} | '
                f'{row.average_net_return * 100:.4f} | '
                f'{row.win_rate_pct:.2f} | '
                f'{"yes" if row.meets_minimum_sample else "no"} |'
            )
        lines.append('')
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def _run_slice(
    *,
    data_root: Path,
    output_root: Path,
    symbol: str,
    timeframe: str,
    year: int,
) -> FactorResearchSlice:
    safe_symbol = symbol.replace('/', '_')
    try:
        merged_dir = validate_strategies._materialize_validation_data_dir(
            data_root,
            symbol=symbol,
            timeframe=timeframe,
        )
        engine = BacktestEngine(data_dir=merged_dir)
        entry = engine.load_data(merged_dir / f'{safe_symbol}_{timeframe}.csv')
        hour = engine.load_data(merged_dir / f'{safe_symbol}_1h.csv')
        four_hour = engine.load_data(merged_dir / f'{safe_symbol}_4h.csv')
        events = build_key_level_event_dataset(
            entry,
            hour,
            four_hour,
            timeframe=timeframe,
        )
        events = _calendar_year_slice(events, year=year)
        if events.empty:
            return _unavailable_slice(
                symbol,
                timeframe,
                year,
                'merged data has no key-level events in the requested calendar year',
            )
        output_root.mkdir(parents=True, exist_ok=True)
        dataset_path = output_root / f'{safe_symbol}_{timeframe}_{year}_key_level_events.csv'
        events.to_csv(dataset_path)
        summary = summarize_one_hour_factor_buckets(events)
        status = 'COMPLETE_YEAR' if _covers_calendar_year(entry, year=year) else 'PARTIAL_YEAR'
        return FactorResearchSlice(
            symbol=symbol,
            timeframe=timeframe,
            year=year,
            status=status,
            events=len(events),
            dataset_path=dataset_path,
            summary=summary,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _unavailable_slice(symbol, timeframe, year, str(exc))


def _calendar_year_slice(
    events: pd.DataFrame,
    *,
    year: int,
) -> pd.DataFrame:
    start = pd.Timestamp(f'{year}-01-01', tz='UTC')
    end = pd.Timestamp(f'{year + 1}-01-01', tz='UTC')
    return events.loc[(events.index >= start) & (events.index < end)].copy()


def _covers_calendar_year(entry: pd.DataFrame, *, year: int) -> bool:
    start = pd.Timestamp(entry.index.min())
    end = pd.Timestamp(entry.index.max())
    year_start = pd.Timestamp(f'{year}-01-01', tz='UTC')
    next_year_start = pd.Timestamp(f'{year + 1}-01-01', tz='UTC')
    return start <= year_start and end >= next_year_start - pd.Timedelta(minutes=15)


def _unavailable_slice(
    symbol: str,
    timeframe: str,
    year: int,
    error: str,
) -> FactorResearchSlice:
    return FactorResearchSlice(
        symbol=symbol,
        timeframe=timeframe,
        year=year,
        status='DATA_UNAVAILABLE',
        events=0,
        dataset_path=None,
        summary=pd.DataFrame(),
        error=error,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate key-level event factor research.')
    parser.add_argument(
        '--output',
        type=Path,
        default=PROJECT_ROOT / 'docs' / 'research' / 'event-factor-report.md',
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = _parse_args()
    slices = run_event_factor_research()
    write_factor_report(slices, args.output)
    logger.info('slices=%s output=%s', len(slices), args.output)


if __name__ == '__main__':
    main()
