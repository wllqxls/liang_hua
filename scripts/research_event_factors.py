"""Generate read-only event factor datasets and reports."""

from __future__ import annotations

import argparse
import logging
import math
import subprocess
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
    VolumeAbsorptionEventStudy,
    build_key_level_event_dataset,
    build_volume_absorption_event_study,
    summarize_absorption_reversal_buckets,
    summarize_one_hour_factor_buckets,
)


logger = logging.getLogger(__name__)
SYMBOLS = ('BTC/USDT', 'ETH/USDT')
TIMEFRAMES = ('5m', '15m')
YEARS = (2025, 2026)
ABSORPTION_YEARS = (2024, 2025)


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


@dataclass(frozen=True, slots=True)
class AbsorptionResearchSlice:
    symbol: str
    timeframe: str
    year: int
    status: str
    event_a_count: int
    event_b_count: int
    conversion_rate: float
    event_a_dataset_path: Path | None
    event_b_dataset_path: Path | None
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


def run_absorption_event_research(
    *,
    data_root: Path = PROJECT_ROOT / 'data',
    output_root: Path = PROJECT_ROOT / 'results' / 'research',
    symbols: Sequence[str] = SYMBOLS,
    timeframe: str = '5m',
    years: Sequence[int] = ABSORPTION_YEARS,
) -> list[AbsorptionResearchSlice]:
    """Build each absorption study once per symbol, then slice by UTC year."""
    slices: list[AbsorptionResearchSlice] = []
    for symbol in symbols:
        try:
            safe_symbol = symbol.replace('/', '_')
            merged_dir = validate_strategies._materialize_validation_data_dir(
                data_root,
                symbol=symbol,
                timeframe=timeframe,
            )
            engine = BacktestEngine(data_dir=merged_dir)
            entry = engine.load_data(merged_dir / f'{safe_symbol}_{timeframe}.csv')
            study = build_volume_absorption_event_study(entry, timeframe=timeframe)
        except (FileNotFoundError, ValueError) as exc:
            slices.extend(
                _unavailable_absorption_slice(
                    symbol,
                    timeframe,
                    year,
                    str(exc),
                )
                for year in years
            )
            continue
        for year in years:
            slices.append(
                _slice_absorption_study(
                    study=study,
                    entry=entry,
                    output_root=output_root,
                    symbol=symbol,
                    timeframe=timeframe,
                    year=year,
                )
            )
    return slices


def write_absorption_report(
    slices: Sequence[AbsorptionResearchSlice],
    output_path: Path,
    *,
    ran_15m: bool,
) -> None:
    """Write absorption statistics and the predeclared 15m stop decision."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Volume-Absorption Reversal Event Factor Report',
        '',
        '- Scope: read-only event research; no strategy or trade is created.',
        f'- Fixed single-symbol round-trip cost: `{FIXED_ROUND_TRIP_COST:.4f}`.',
        '- Event A: volume ratio >= 3.0, true range / ATR <= 0.8, three-bar displacement >= 1.0 ATR.',
        '- Event B: within three bars, price moves at least 0.5 event ATR in the contrarian direction.',
        '- 15m gate: all four BTC/ETH 2024/2025 5m slices must have positive net one-hour average return.',
        f'- 15m executed: `{"yes" if ran_15m else "no"}`.',
        '- Design: `docs/research/volume-absorption-design.md`.',
        f'- Code revision: `{_git_revision()}`.',
        '',
    ]
    for item in slices:
        lines.extend(
            [
                f'## {item.symbol} / {item.timeframe} / {item.year}',
                '',
                f'- Status: `{item.status}`',
                f'- Event A: `{item.event_a_count}`',
                f'- Event B: `{item.event_b_count}`',
                f'- A→B conversion: `{item.conversion_rate * 100:.2f}%`',
            ]
        )
        if item.event_a_dataset_path is not None:
            lines.append(f'- A dataset: `{item.event_a_dataset_path.as_posix()}`')
        if item.event_b_dataset_path is not None:
            lines.append(f'- B dataset: `{item.event_b_dataset_path.as_posix()}`')
        if item.error is not None:
            lines.append(f'- Data note: {item.error}')
        if item.summary.empty:
            lines.extend(['', 'No one-hour absorption buckets available.', ''])
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
                f'{row.win_rate_pct:.2f} | '
                f'{_format_profit_factor(row.profit_factor)} | '
                f'{"yes" if row.meets_minimum_sample else "no"} |'
            )
        lines.append('')
    if not ran_15m:
        lines.extend(
            [
                '## Stop decision',
                '',
                'At least one 5m BTC/ETH 2024/2025 slice did not have a positive net one-hour average return. Per the frozen gate, 15m was not run.',
                '',
            ]
        )
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def _should_run_absorption_15m(
    slices: Sequence[AbsorptionResearchSlice],
) -> bool:
    expected = {(symbol, year) for symbol in SYMBOLS for year in ABSORPTION_YEARS}
    actual = {(item.symbol, item.year) for item in slices if item.timeframe == '5m'}
    if actual != expected:
        return False
    for item in slices:
        if item.timeframe != '5m' or item.status == 'DATA_UNAVAILABLE':
            return False
        overall = item.summary.loc[item.summary['factor'] == 'overall']
        if len(overall) != 1 or float(overall.iloc[0]['average_net_return']) <= 0:
            return False
    return True


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


def _slice_absorption_study(
    *,
    study: VolumeAbsorptionEventStudy,
    entry: pd.DataFrame,
    output_root: Path,
    symbol: str,
    timeframe: str,
    year: int,
) -> AbsorptionResearchSlice:
    event_a = _calendar_year_slice(study.event_a, year=year)
    event_b = _absorption_b_for_source_year(study.event_b, year=year)
    if event_a.empty:
        return _unavailable_absorption_slice(
            symbol,
            timeframe,
            year,
            'merged data has no volume-absorption A events in the requested calendar year',
        )
    safe_symbol = symbol.replace('/', '_')
    output_root.mkdir(parents=True, exist_ok=True)
    event_a_path = output_root / f'{safe_symbol}_{timeframe}_{year}_volume_absorption_a.csv'
    event_b_path = output_root / f'{safe_symbol}_{timeframe}_{year}_volume_absorption_b.csv'
    event_a.to_csv(event_a_path)
    event_b.to_csv(event_b_path)
    return AbsorptionResearchSlice(
        symbol=symbol,
        timeframe=timeframe,
        year=year,
        status='COMPLETE_YEAR' if _covers_calendar_year(entry, year=year) else 'PARTIAL_YEAR',
        event_a_count=len(event_a),
        event_b_count=int(event_a['converted_to_b'].sum()),
        conversion_rate=float(event_a['converted_to_b'].mean()),
        event_a_dataset_path=event_a_path,
        event_b_dataset_path=event_b_path,
        summary=summarize_absorption_reversal_buckets(event_a),
    )


def _absorption_b_for_source_year(
    event_b: pd.DataFrame,
    *,
    year: int,
) -> pd.DataFrame:
    if event_b.empty:
        return event_b.copy()
    source_time = pd.to_datetime(event_b['source_event_time'], utc=True)
    start = pd.Timestamp(f'{year}-01-01', tz='UTC')
    end = pd.Timestamp(f'{year + 1}-01-01', tz='UTC')
    return event_b.loc[(source_time >= start) & (source_time < end)].copy()


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


def _unavailable_absorption_slice(
    symbol: str,
    timeframe: str,
    year: int,
    error: str,
) -> AbsorptionResearchSlice:
    return AbsorptionResearchSlice(
        symbol=symbol,
        timeframe=timeframe,
        year=year,
        status='DATA_UNAVAILABLE',
        event_a_count=0,
        event_b_count=0,
        conversion_rate=0.0,
        event_a_dataset_path=None,
        event_b_dataset_path=None,
        summary=pd.DataFrame(),
        error=error,
    )


def _format_profit_factor(value: float) -> str:
    return 'N/A' if not math.isfinite(value) else f'{value:.3f}'


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
    parser = argparse.ArgumentParser(description='Generate read-only event factor research.')
    parser.add_argument(
        '--hypothesis',
        choices=('key_level', 'volume_absorption'),
        default='key_level',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=None,
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = _parse_args()
    if args.hypothesis == 'volume_absorption':
        output = args.output or PROJECT_ROOT / 'docs' / 'research' / 'volume-absorption-report.md'
        five_minute_slices = run_absorption_event_research(timeframe='5m')
        ran_15m = _should_run_absorption_15m(five_minute_slices)
        all_slices = list(five_minute_slices)
        if ran_15m:
            all_slices.extend(run_absorption_event_research(timeframe='15m'))
        write_absorption_report(all_slices, output, ran_15m=ran_15m)
        logger.info(
            'hypothesis=volume_absorption slices=%s ran_15m=%s output=%s',
            len(all_slices),
            ran_15m,
            output,
        )
        return
    output = args.output or PROJECT_ROOT / 'docs' / 'research' / 'event-factor-report.md'
    slices = run_event_factor_research()
    write_factor_report(slices, output)
    logger.info('hypothesis=key_level slices=%s output=%s', len(slices), output)


if __name__ == '__main__':
    main()
