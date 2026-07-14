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
    LEAD_LAG_BTC_IMPULSE_ATR_THRESHOLD,
    LEAD_LAG_ETH_RELATIVE_THRESHOLD,
    MINIMUM_BUCKET_SAMPLES,
    RANGE_ATR_THRESHOLD,
    ReturnDistributionSummary,
    TREND_CUMULATIVE_RETURN_THRESHOLD,
    VOLUME_SHOCK_THRESHOLD,
    VolumeAbsorptionEventStudy,
    build_hourly_extreme_reversion_dataset,
    build_btc_eth_lead_lag_dataset,
    build_key_level_event_dataset,
    build_trend_inertia_event_dataset,
    build_volume_absorption_event_study,
    summarize_absorption_reversal_buckets,
    summarize_hourly_extreme_reversion,
    summarize_btc_eth_lead_lag,
    summarize_return_distribution,
    summarize_one_hour_factor_buckets,
    summarize_trend_inertia_horizons,
)


logger = logging.getLogger(__name__)
SYMBOLS = ('BTC/USDT', 'ETH/USDT')
TIMEFRAMES = ('5m', '15m')
YEARS = (2025, 2026)
ABSORPTION_YEARS = (2024, 2025)
_RESEARCH_MATRIX_SPECS = (
    (
        'Key-level breakout/reversal',
        '1h',
        'BTC/ETH 5m+15m, 2025',
        tuple(
            f'{symbol}_{timeframe}_2025_key_level_events.csv'
            for symbol in ('BTC_USDT', 'ETH_USDT')
            for timeframe in ('5m', '15m')
        ),
    ),
    (
        'Volatility-compression breakout',
        '1h',
        'BTC/ETH 5m, 2025',
        tuple(
            f'{symbol}_5m_2025_volatility_breakout_b.csv'
            for symbol in ('BTC_USDT', 'ETH_USDT')
        ),
    ),
    (
        'Extreme-momentum next-bar reversion',
        '1h',
        'BTC/ETH 5m, 2024–2025',
        tuple(
            f'{symbol}_5m_{year}_momentum_reversion_a.csv'
            for symbol in ('BTC_USDT', 'ETH_USDT')
            for year in ABSORPTION_YEARS
        ),
    ),
    (
        'Volume-absorption reversal',
        '1h',
        'BTC/ETH 5m+15m, 2024–2025',
        tuple(
            f'{symbol}_{timeframe}_{year}_volume_absorption_a.csv'
            for symbol in ('BTC_USDT', 'ETH_USDT')
            for timeframe in ('5m', '15m')
            for year in ABSORPTION_YEARS
        ),
    ),
    (
        'Three-bar trend inertia',
        '1h',
        'BTC/ETH 5m+15m, 2024–2025',
        tuple(
            f'{symbol}_{timeframe}_{year}_trend_inertia.csv'
            for symbol in ('BTC_USDT', 'ETH_USDT')
            for timeframe in ('5m', '15m')
            for year in ABSORPTION_YEARS
        ),
    ),
    (
        'Hourly extreme-momentum reversion',
        '2h',
        'BTC/ETH 1h, 2024–2025',
        tuple(
            f'{symbol}_1h_{year}_hourly_extreme_reversion.csv'
            for symbol in ('BTC_USDT', 'ETH_USDT')
            for year in ABSORPTION_YEARS
        ),
    ),
    (
        'BTC→ETH short-term lead-lag',
        '15m',
        'BTC signal / ETH return, 5m 2024–2025',
        tuple(
            f'BTC_ETH_5m_{year}_lead_lag.csv'
            for year in ABSORPTION_YEARS
        ),
    ),
)


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


@dataclass(frozen=True, slots=True)
class LeadLagResearchSlice:
    year: int
    status: str
    events: int
    side_counts: dict[str, int]
    dataset_path: Path | None
    summary: pd.DataFrame
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchMatrixRow:
    hypothesis: str
    primary_horizon: str
    data_scope: str
    source_slices: int
    metrics: ReturnDistributionSummary
    status: str


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
    result_rows = [
        (item, row)
        for item in slices
        for row in item.summary.itertuples(index=False)
    ]
    if result_rows:
        sample_counts = [int(row.samples) for _, row in result_rows]
        all_net_negative = all(row.average_net_return < 0 for _, row in result_rows)
        all_pf_below_one = all(row.profit_factor < 1 for _, row in result_rows)
        positive_gross = [
            f'{item.symbol} {item.year} {row.horizon} `{row.average_gross_return * 100:+.4f}%`'
            for item, row in result_rows
            if row.average_gross_return > 0
        ]
        lines.extend(
            [
                '',
                '## Conclusion',
                '',
                f'- All net averages negative: `{"yes" if all_net_negative else "no"}`; all net Profit Factors below `1.0`: `{"yes" if all_pf_below_one else "no"}`.',
                f'- Samples per result: `{min(sample_counts)}–{max(sample_counts)}`; this is not a small-sample rejection.',
                f'- Positive gross exceptions: {", ".join(positive_gross) if positive_gross else "none"}.',
                '- Per the predeclared decision, if every net result is negative, the project stops tuning single-symbol short-horizon extreme-momentum mean-reversion rules. This rejects the tested basic family; it is not a mathematical claim that every possible mean-reversion model is impossible.',
                '',
            ]
        )
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def run_btc_eth_lead_lag_research(
    *,
    data_root: Path = PROJECT_ROOT / 'data',
    output_root: Path = PROJECT_ROOT / 'results' / 'research',
    years: Sequence[int] = ABSORPTION_YEARS,
) -> list[LeadLagResearchSlice]:
    """Run the paired 5m study without reading the reserved 2026 data."""
    try:
        btc = _load_year_frames(
            data_root,
            symbol='BTC/USDT',
            timeframe='5m',
            years=years,
        )
        eth = _load_year_frames(
            data_root,
            symbol='ETH/USDT',
            timeframe='5m',
            years=years,
        )
        events = build_btc_eth_lead_lag_dataset(btc, eth)
    except (FileNotFoundError, ValueError) as exc:
        return [
            _unavailable_lead_lag_slice(year, str(exc))
            for year in years
        ]
    return [
        _slice_btc_eth_lead_lag_events(
            events=events,
            btc=btc,
            eth=eth,
            output_root=output_root,
            year=year,
        )
        for year in years
    ]


def write_btc_eth_lead_lag_report(
    slices: Sequence[LeadLagResearchSlice],
    output_path: Path,
) -> None:
    """Write paired lead-lag results and the frozen 15m promotion gate."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    passed = _lead_lag_gate_passed(slices)
    result_rows = [
        (item, row)
        for item in slices
        for row in item.summary.itertuples(index=False)
    ]
    all_net_negative = bool(result_rows) and all(
        row.average_net_return < 0 for _, row in result_rows
    )
    primary_gross_negative = bool(slices) and all(
        len(item.summary.loc[item.summary['horizon'] == '15m']) == 1
        and float(
            item.summary.loc[item.summary['horizon'] == '15m'].iloc[0][
                'average_gross_return'
            ]
        ) < 0
        for item in slices
    )
    lines = [
        '# BTC→ETH Short-Term Lead-Lag Event Factor Report',
        '',
        '- Scope: read-only event research; no strategy or trade is created.',
        '- Data read: synchronized BTC/ETH 5m candles from UTC 2024 and 2025 only; 2026 remains unused.',
        f'- BTC impulse threshold: `{LEAD_LAG_BTC_IMPULSE_ATR_THRESHOLD:.1f} ATR(14)` over three bars.',
        f'- ETH lag rule: same direction and normalized displacement <= `{LEAD_LAG_ETH_RELATIVE_THRESHOLD:.1f}` of BTC.',
        f'- Fixed ETH single-leg complete round-trip cost: `{FIXED_ROUND_TRIP_COST:.4f}`.',
        '- Primary gate horizon: `15m`; 5m/30m/1h are diagnostic only.',
        '- Confidence interval: deterministic UTC-calendar-day block bootstrap, 95%.',
        '- Design: `docs/research/btc-eth-lead-lag-design.md`.',
        f'- Code revision: `{_git_revision()}`.',
        '',
        '| Year | Horizon | Samples | Gross positive % | Avg gross % | Avg net % | Break-even cost % | Net mean 95% CI % | Net PF | Status |',
        '|---:|---|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for item in slices:
        if item.summary.empty:
            lines.append(
                f'| {item.year} | N/A | 0 | 0.00 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | {item.status} |'
            )
            continue
        for row in item.summary.itertuples(index=False):
            lines.append(
                f'| {item.year} | {row.horizon} | {row.samples} | '
                f'{row.positive_rate_pct:.2f} | '
                f'{row.average_gross_return * 100:.4f} | '
                f'{row.average_net_return * 100:.4f} | '
                f'{row.break_even_round_trip_cost * 100:.4f} | '
                f'[{row.net_mean_ci_lower * 100:.4f}, {row.net_mean_ci_upper * 100:.4f}] | '
                f'{_format_profit_factor(row.profit_factor)} | {item.status} |'
            )
    lines.extend(['', '## Event direction composition', ''])
    for item in slices:
        side_text = ', '.join(
            f'{side}={count}' for side, count in sorted(item.side_counts.items())
        ) or 'none'
        lines.append(f'- {item.year}: {side_text}')
    lines.extend(
        [
            '',
            '## Frozen 15m gate',
            '',
            f'- Passed: `{"yes" if passed else "no"}`.',
            '- Required in both years: samples >= 200, average net return > 0, net PF >= 1.15, and net mean 95% CI lower bound > 0.',
            f'- Strategy generated: `no`.',
            '',
            '## Conclusion',
            '',
            f'- All tested horizons have negative net means: `{"yes" if all_net_negative else "no"}`.',
            f'- The primary 15m gross mean is negative in both years: `{"yes" if primary_gross_negative else "no"}`.',
            '- If the primary gross mean is already negative, lower execution cost cannot turn this frozen event definition into a stable edge.',
            '',
        ]
    )
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def build_research_matrix(
    *,
    results_root: Path = PROJECT_ROOT / 'results' / 'research',
) -> list[ResearchMatrixRow]:
    """Pool each frozen study at its primary horizon for comparable metrics."""
    rows: list[ResearchMatrixRow] = []
    for hypothesis, horizon, scope, filenames in _RESEARCH_MATRIX_SPECS:
        gross_parts: list[pd.Series] = []
        block_parts: list[pd.Series] = []
        missing_files: list[str] = []
        for filename in filenames:
            path = results_root / filename
            if not path.exists():
                missing_files.append(filename)
                continue
            frame = pd.read_csv(path, index_col=0)
            gross_column = f'forward_return_{horizon}'
            if gross_column not in frame:
                raise ValueError(f'{filename} is missing required column: {gross_column}')
            timestamps = pd.to_datetime(frame.index, utc=True, errors='coerce')
            gross = pd.to_numeric(frame[gross_column], errors='coerce').reset_index(drop=True)
            blocks = pd.Series(
                [
                    f'{filename}|{timestamp.floor("D").isoformat()}'
                    if not pd.isna(timestamp)
                    else None
                    for timestamp in timestamps
                ]
            )
            gross_parts.append(gross)
            block_parts.append(blocks)
        if not gross_parts:
            metrics = summarize_return_distribution(pd.Series(dtype=float), block_ids=[])
        else:
            metrics = summarize_return_distribution(
                pd.concat(gross_parts, ignore_index=True),
                block_ids=pd.concat(block_parts, ignore_index=True),
            )
        rows.append(
            ResearchMatrixRow(
                hypothesis=hypothesis,
                primary_horizon=horizon,
                data_scope=scope,
                source_slices=len(filenames) - len(missing_files),
                metrics=metrics,
                status='COMPLETE' if not missing_files else f'MISSING_{len(missing_files)}_SLICES',
            )
        )
    return rows


def write_research_matrix_report(
    rows: Sequence[ResearchMatrixRow],
    output_path: Path,
) -> None:
    """Write one comparable table across all completed base hypotheses."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Unified Rejected-Event Research Matrix',
        '',
        '- Each hypothesis is pooled only at its predeclared representative horizon.',
        f'- All net returns deduct the same single-symbol complete round-trip cost `{FIXED_ROUND_TRIP_COST:.4f}`.',
        '- Break-even cost equals the average gross return; a negative value means no non-negative execution cost can rescue the pooled mean.',
        '- The 95% interval is a deterministic source-slice × UTC-day block bootstrap of the net mean.',
        '- Pooled results are descriptive and do not replace the stricter cross-year and cross-symbol rejection already recorded in each report.',
        f'- Code revision: `{_git_revision()}`.',
        '',
        '| Hypothesis | Primary horizon | Data scope | Slices | Events | Avg gross % | Avg net % | Break-even cost % | Net mean 95% CI % | Net PF | Status |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        metrics = row.metrics
        lines.append(
            f'| {row.hypothesis} | {row.primary_horizon} | {row.data_scope} | '
            f'{row.source_slices} | {metrics.samples} | '
            f'{metrics.average_gross_return * 100:.4f} | '
            f'{metrics.average_net_return * 100:.4f} | '
            f'{metrics.break_even_round_trip_cost * 100:.4f} | '
            f'[{metrics.net_mean_ci_lower * 100:.4f}, {metrics.net_mean_ci_upper * 100:.4f}] | '
            f'{_format_profit_factor(metrics.profit_factor)} | {row.status} |'
        )
    lines.extend(
        [
            '',
            '## Reading rule',
            '',
            'A useful raw factor would need a positive gross mean large enough to cover cost and a net confidence interval that does not straddle zero. A large event count alone is not evidence of edge.',
            '',
        ]
    )
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


def _load_year_frames(
    data_root: Path,
    *,
    symbol: str,
    timeframe: str,
    years: Sequence[int],
) -> pd.DataFrame:
    safe_symbol = symbol.replace('/', '_')
    frames: list[pd.DataFrame] = []
    for year in years:
        year_dir = data_root / str(year)
        path = year_dir / f'{safe_symbol}_{timeframe}.csv'
        frames.append(BacktestEngine(data_dir=year_dir).load_data(path))
    combined = pd.concat(frames).sort_index()
    return combined.loc[~combined.index.duplicated(keep='last')]


def _slice_btc_eth_lead_lag_events(
    *,
    events: pd.DataFrame,
    btc: pd.DataFrame,
    eth: pd.DataFrame,
    output_root: Path,
    year: int,
) -> LeadLagResearchSlice:
    year_events = _calendar_year_slice(events, year=year)
    if year_events.empty:
        return _unavailable_lead_lag_slice(
            year,
            'paired data has no BTC→ETH lead-lag events in the requested calendar year',
        )
    output_root.mkdir(parents=True, exist_ok=True)
    dataset_path = output_root / f'BTC_ETH_5m_{year}_lead_lag.csv'
    year_events.to_csv(dataset_path)
    complete = _covers_calendar_year(btc, year=year, timeframe='5m') and _covers_calendar_year(
        eth,
        year=year,
        timeframe='5m',
    )
    return LeadLagResearchSlice(
        year=year,
        status='COMPLETE_YEAR' if complete else 'PARTIAL_YEAR',
        events=len(year_events),
        side_counts={
            str(side): int(count)
            for side, count in year_events['side'].value_counts().items()
        },
        dataset_path=dataset_path,
        summary=summarize_btc_eth_lead_lag(year_events),
    )


def _lead_lag_gate_passed(slices: Sequence[LeadLagResearchSlice]) -> bool:
    if {item.year for item in slices} != set(ABSORPTION_YEARS):
        return False
    for item in slices:
        if item.status != 'COMPLETE_YEAR':
            return False
        primary = item.summary.loc[item.summary['horizon'] == '15m']
        if len(primary) != 1:
            return False
        row = primary.iloc[0]
        if not (
            int(row['samples']) >= MINIMUM_BUCKET_SAMPLES
            and float(row['average_net_return']) > 0
            and float(row['profit_factor']) >= 1.15
            and float(row['net_mean_ci_lower']) > 0
        ):
            return False
    return True


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


def _unavailable_lead_lag_slice(
    year: int,
    error: str,
) -> LeadLagResearchSlice:
    return LeadLagResearchSlice(
        year=year,
        status='DATA_UNAVAILABLE',
        events=0,
        side_counts={},
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
            'btc_eth_lead_lag',
            'research_matrix',
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
    if args.hypothesis == 'research_matrix':
        output = args.output or PROJECT_ROOT / 'docs' / 'research' / 'unified-research-matrix.md'
        rows = build_research_matrix()
        write_research_matrix_report(rows, output)
        logger.info(
            'hypothesis=research_matrix rows=%s output=%s',
            len(rows),
            output,
        )
        return
    if args.hypothesis == 'btc_eth_lead_lag':
        output = args.output or PROJECT_ROOT / 'docs' / 'research' / 'btc-eth-lead-lag-report.md'
        slices = run_btc_eth_lead_lag_research()
        write_btc_eth_lead_lag_report(slices, output)
        logger.info(
            'hypothesis=btc_eth_lead_lag slices=%s output=%s',
            len(slices),
            output,
        )
        return
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
