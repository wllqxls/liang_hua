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
    HOURLY_BODY_THRESHOLD,
    HOURLY_REVERSAL_ATR_THRESHOLD,
    HOURLY_TWO_BAR_MOVE_THRESHOLD,
    RANGE_ATR_THRESHOLD,
    TREND_CUMULATIVE_RETURN_THRESHOLD,
    VOLUME_SHOCK_THRESHOLD,
    VolumeAbsorptionEventStudy,
    build_hourly_extreme_reversion_dataset,
    build_key_level_event_dataset,
    build_trend_inertia_event_dataset,
    build_volume_absorption_event_study,
    summarize_absorption_reversal_buckets,
    summarize_hourly_extreme_reversion,
    summarize_one_hour_factor_buckets,
    summarize_trend_inertia_horizons,
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


@dataclass(frozen=True, slots=True)
class TrendInertiaResearchSlice:
    symbol: str
    timeframe: str
    year: int
    status: str
    events: int
    dataset_path: Path | None
    summary: pd.DataFrame
    error: str | None = None


@dataclass(frozen=True, slots=True)
class HourlyExtremeReversionSlice:
    symbol: str
    year: int
    status: str
    events: int
    trigger_counts: dict[str, int]
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
        f'- Event A: volume ratio >= {VOLUME_SHOCK_THRESHOLD:.1f}, true range / ATR <= {RANGE_ATR_THRESHOLD:.1f}, three-bar displacement >= 1.0 ATR.',
        '- Event B: within three bars, price moves at least 0.5 event ATR in the contrarian direction.',
        '- Timeframes: 5m and 15m are executed as a predeclared parallel comparison.',
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


def run_trend_inertia_research(
    *,
    data_root: Path = PROJECT_ROOT / 'data',
    output_root: Path = PROJECT_ROOT / 'results' / 'research',
    symbols: Sequence[str] = SYMBOLS,
    timeframes: Sequence[str] = TIMEFRAMES,
    years: Sequence[int] = ABSORPTION_YEARS,
) -> list[TrendInertiaResearchSlice]:
    """Run trend events on each entry timeframe with exact 5m labels."""
    slices: list[TrendInertiaResearchSlice] = []
    for symbol in symbols:
        safe_symbol = symbol.replace('/', '_')
        try:
            label_dir = validate_strategies._materialize_validation_data_dir(
                data_root,
                symbol=symbol,
                timeframe='5m',
            )
            five_minute = BacktestEngine(data_dir=label_dir).load_data(
                label_dir / f'{safe_symbol}_5m.csv'
            )
        except (FileNotFoundError, ValueError) as exc:
            slices.extend(
                _unavailable_trend_slice(symbol, timeframe, year, str(exc))
                for timeframe in timeframes
                for year in years
            )
            continue
        for timeframe in timeframes:
            try:
                entry_dir = validate_strategies._materialize_validation_data_dir(
                    data_root,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                entry = BacktestEngine(data_dir=entry_dir).load_data(
                    entry_dir / f'{safe_symbol}_{timeframe}.csv'
                )
                events = build_trend_inertia_event_dataset(
                    entry,
                    five_minute,
                    timeframe=timeframe,
                )
            except (FileNotFoundError, ValueError) as exc:
                slices.extend(
                    _unavailable_trend_slice(symbol, timeframe, year, str(exc))
                    for year in years
                )
                continue
            for year in years:
                slices.append(
                    _slice_trend_inertia_events(
                        events=events,
                        entry=entry,
                        output_root=output_root,
                        symbol=symbol,
                        timeframe=timeframe,
                        year=year,
                    )
                )
    return slices


def write_trend_inertia_report(
    slices: Sequence[TrendInertiaResearchSlice],
    output_path: Path,
) -> None:
    """Write separate 5m and 15m event result tables."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Short-Term Trend Inertia Event Factor Report',
        '',
        '- Scope: read-only event research; no strategy or trade is created.',
        f'- Event threshold: three same-sign close returns and cumulative absolute return >= `{TREND_CUMULATIVE_RETURN_THRESHOLD:.4f}`.',
        f'- Fixed round-trip cost: `{FIXED_ROUND_TRIP_COST:.4f}`.',
        '- Conversion: gross directional return > 0 at the exact 5m, 15m, or 1h horizon.',
        '- 15m event 5m labels come from synchronized raw 5m closes.',
        '- Design: `docs/research/trend-inertia-design.md`.',
        f'- Code revision: `{_git_revision()}`.',
        '',
    ]
    for timeframe in TIMEFRAMES:
        lines.extend(
            [
                f'## {timeframe} event results',
                '',
                '| Slice | Horizon | Samples | Gross continuation % | Avg gross return % | Avg net return % | Net Profit Factor | Status |',
                '|---|---|---:|---:|---:|---:|---:|---|',
            ]
        )
        timeframe_slices = [item for item in slices if item.timeframe == timeframe]
        for item in timeframe_slices:
            if item.summary.empty:
                lines.append(
                    f'| {item.symbol} {item.year} | N/A | 0 | 0.00 | 0.0000 | 0.0000 | N/A | {item.status} |'
                )
                continue
            for row in item.summary.itertuples(index=False):
                lines.append(
                    f'| {item.symbol} {item.year} | {row.horizon} | {row.samples} | '
                    f'{row.conversion_rate_pct:.2f} | '
                    f'{row.average_gross_return * 100:.4f} | '
                    f'{row.average_net_return * 100:.4f} | '
                    f'{_format_profit_factor(row.profit_factor)} | {item.status} |'
                )
        lines.append('')
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def run_hourly_extreme_reversion_research(
    *,
    data_root: Path = PROJECT_ROOT / 'data',
    output_root: Path = PROJECT_ROOT / 'results' / 'research',
    symbols: Sequence[str] = SYMBOLS,
    years: Sequence[int] = ABSORPTION_YEARS,
) -> list[HourlyExtremeReversionSlice]:
    """Build the frozen 1h extreme-reversion study and slice by UTC year."""
    slices: list[HourlyExtremeReversionSlice] = []
    for symbol in symbols:
        safe_symbol = symbol.replace('/', '_')
        try:
            merged_dir = validate_strategies._materialize_validation_data_dir(
                data_root,
                symbol=symbol,
                timeframe='1h',
            )
            hour = BacktestEngine(data_dir=merged_dir).load_data(
                merged_dir / f'{safe_symbol}_1h.csv'
            )
            events = build_hourly_extreme_reversion_dataset(hour)
        except (FileNotFoundError, ValueError) as exc:
            slices.extend(
                _unavailable_hourly_reversion_slice(symbol, year, str(exc))
                for year in years
            )
            continue
        for year in years:
            slices.append(
                _slice_hourly_extreme_reversion_events(
                    events=events,
                    hour=hour,
                    output_root=output_root,
                    symbol=symbol,
                    year=year,
                )
            )
    return slices


def write_hourly_extreme_reversion_report(
    slices: Sequence[HourlyExtremeReversionSlice],
    output_path: Path,
) -> None:
    """Write the fifth-round 1h event study without deriving a strategy."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Hourly Extreme-Momentum Reversion Event Factor Report',
        '',
        '- Scope: read-only event research; no strategy or trade is created.',
        '- Data: BTC/USDT and ETH/USDT, UTC calendar years 2024 and 2025, 1h candles.',
        f'- Two-bar extreme: both bodies >= `{HOURLY_BODY_THRESHOLD:.4f}` and cumulative move >= `{HOURLY_TWO_BAR_MOVE_THRESHOLD:.4f}`.',
        f'- Single-bar extreme: body >= `{HOURLY_BODY_THRESHOLD:.4f}` and close beyond Bollinger(20, 2).',
        f'- Event B: contrarian close movement >= `{HOURLY_REVERSAL_ATR_THRESHOLD:.1f} * ATR(14)` within one or two bars.',
        f'- Fixed complete round-trip cost: `{FIXED_ROUND_TRIP_COST:.4f}`.',
        '- One event is retained per continuous same-direction extreme episode.',
        '- Design: `docs/research/hourly-extreme-reversion-design.md`.',
        f'- Code revision: `{_git_revision()}`.',
        '',
        '| Slice | Horizon | A events | B conversion % | Avg gross return % | Avg net return % | Net Profit Factor | Status |',
        '|---|---|---:|---:|---:|---:|---:|---|',
    ]
    for item in slices:
        if item.summary.empty:
            lines.append(
                f'| {item.symbol} {item.year} | N/A | 0 | 0.00 | 0.0000 | 0.0000 | N/A | {item.status} |'
            )
            continue
        for row in item.summary.itertuples(index=False):
            lines.append(
                f'| {item.symbol} {item.year} | {row.horizon} | {row.samples} | '
                f'{row.reversal_rate_pct:.2f} | '
                f'{row.average_gross_return * 100:.4f} | '
                f'{row.average_net_return * 100:.4f} | '
                f'{_format_profit_factor(row.profit_factor)} | {item.status} |'
            )
    lines.extend(['', '## Event A trigger composition', ''])
    for item in slices:
        trigger_text = ', '.join(
            f'{trigger}={count}' for trigger, count in sorted(item.trigger_counts.items())
        ) or 'none'
        lines.append(f'- {item.symbol} {item.year}: {trigger_text}')
    lines.append('')
    output_path.write_text('\n'.join(lines), encoding='utf-8')


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


def _slice_trend_inertia_events(
    *,
    events: pd.DataFrame,
    entry: pd.DataFrame,
    output_root: Path,
    symbol: str,
    timeframe: str,
    year: int,
) -> TrendInertiaResearchSlice:
    year_events = _calendar_year_slice(events, year=year)
    if year_events.empty:
        return _unavailable_trend_slice(
            symbol,
            timeframe,
            year,
            'merged data has no trend-inertia events in the requested calendar year',
        )
    safe_symbol = symbol.replace('/', '_')
    output_root.mkdir(parents=True, exist_ok=True)
    dataset_path = output_root / f'{safe_symbol}_{timeframe}_{year}_trend_inertia.csv'
    year_events.to_csv(dataset_path)
    return TrendInertiaResearchSlice(
        symbol=symbol,
        timeframe=timeframe,
        year=year,
        status='COMPLETE_YEAR' if _covers_calendar_year(entry, year=year) else 'PARTIAL_YEAR',
        events=len(year_events),
        dataset_path=dataset_path,
        summary=summarize_trend_inertia_horizons(year_events),
    )


def _slice_hourly_extreme_reversion_events(
    *,
    events: pd.DataFrame,
    hour: pd.DataFrame,
    output_root: Path,
    symbol: str,
    year: int,
) -> HourlyExtremeReversionSlice:
    year_events = _calendar_year_slice(events, year=year)
    if year_events.empty:
        return _unavailable_hourly_reversion_slice(
            symbol,
            year,
            'merged data has no hourly extreme-reversion events in the requested calendar year',
        )
    safe_symbol = symbol.replace('/', '_')
    output_root.mkdir(parents=True, exist_ok=True)
    dataset_path = output_root / f'{safe_symbol}_1h_{year}_hourly_extreme_reversion.csv'
    year_events.to_csv(dataset_path)
    return HourlyExtremeReversionSlice(
        symbol=symbol,
        year=year,
        status='COMPLETE_YEAR' if _covers_calendar_year(hour, year=year, timeframe='1h') else 'PARTIAL_YEAR',
        events=len(year_events),
        trigger_counts={
            str(trigger): int(count)
            for trigger, count in year_events['trigger'].value_counts().items()
        },
        dataset_path=dataset_path,
        summary=summarize_hourly_extreme_reversion(year_events),
    )


def _calendar_year_slice(
    events: pd.DataFrame,
    *,
    year: int,
) -> pd.DataFrame:
    start = pd.Timestamp(f'{year}-01-01', tz='UTC')
    end = pd.Timestamp(f'{year + 1}-01-01', tz='UTC')
    return events.loc[(events.index >= start) & (events.index < end)].copy()


def _covers_calendar_year(
    entry: pd.DataFrame,
    *,
    year: int,
    timeframe: str = '15m',
) -> bool:
    start = pd.Timestamp(entry.index.min())
    end = pd.Timestamp(entry.index.max())
    year_start = pd.Timestamp(f'{year}-01-01', tz='UTC')
    next_year_start = pd.Timestamp(f'{year + 1}-01-01', tz='UTC')
    candle_duration = pd.Timedelta(timeframe)
    return start <= year_start and end >= next_year_start - candle_duration


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


def _unavailable_trend_slice(
    symbol: str,
    timeframe: str,
    year: int,
    error: str,
) -> TrendInertiaResearchSlice:
    return TrendInertiaResearchSlice(
        symbol=symbol,
        timeframe=timeframe,
        year=year,
        status='DATA_UNAVAILABLE',
        events=0,
        dataset_path=None,
        summary=pd.DataFrame(),
        error=error,
    )


def _unavailable_hourly_reversion_slice(
    symbol: str,
    year: int,
    error: str,
) -> HourlyExtremeReversionSlice:
    return HourlyExtremeReversionSlice(
        symbol=symbol,
        year=year,
        status='DATA_UNAVAILABLE',
        events=0,
        trigger_counts={},
        dataset_path=None,
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
        choices=(
            'key_level',
            'volume_absorption',
            'trend_inertia',
            'hourly_extreme_reversion',
        ),
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
    if args.hypothesis == 'hourly_extreme_reversion':
        output = args.output or PROJECT_ROOT / 'docs' / 'research' / 'hourly-extreme-reversion-report.md'
        slices = run_hourly_extreme_reversion_research()
        write_hourly_extreme_reversion_report(slices, output)
        logger.info(
            'hypothesis=hourly_extreme_reversion slices=%s output=%s',
            len(slices),
            output,
        )
        return
    if args.hypothesis == 'trend_inertia':
        output = args.output or PROJECT_ROOT / 'docs' / 'research' / 'trend-inertia-report.md'
        slices = run_trend_inertia_research()
        write_trend_inertia_report(slices, output)
        logger.info(
            'hypothesis=trend_inertia slices=%s output=%s',
            len(slices),
            output,
        )
        return
    if args.hypothesis == 'volume_absorption':
        output = args.output or PROJECT_ROOT / 'docs' / 'research' / 'volume-absorption-report.md'
        five_minute_slices = run_absorption_event_research(timeframe='5m')
        fifteen_minute_slices = run_absorption_event_research(timeframe='15m')
        ran_15m = True
        all_slices = [*five_minute_slices, *fifteen_minute_slices]
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
