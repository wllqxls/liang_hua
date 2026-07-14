"""Run the fixed PULLBACK_CONFIRMATION research matrix outside active strategy flows."""

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
from src.backtest.engine import BacktestEngine, BacktestResult
from src.strategies.signal_models import (
    MarginMode,
    PullbackFilterPreset,
    SignalMode,
    SignalParameters,
)


RESEARCH_MODE = SignalMode.PULLBACK_CONFIRMATION
SYMBOLS = ('BTC/USDT', 'ETH/USDT')
TIMEFRAMES = ('5m', '15m')
YEARS = (2025, 2026)
PRESETS = (PullbackFilterPreset.OFF, PullbackFilterPreset.ALIGN)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResearchRow:
    symbol: str
    timeframe: str
    year: int
    preset: PullbackFilterPreset
    status: str
    reasons: tuple[str, ...]
    avg_window_return_pct: float | None = None
    positive_windows: int | None = None
    annual_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    profit_factor: float | None = None
    annual_trades: int | None = None


def run_research_matrix(
    *,
    data_root: Path = PROJECT_ROOT / 'data',
    symbols: Sequence[str] = SYMBOLS,
    timeframes: Sequence[str] = TIMEFRAMES,
    years: Sequence[int] = YEARS,
    presets: Sequence[PullbackFilterPreset] = PRESETS,
) -> list[ResearchRow]:
    """Run fixed-cost candidate research without making it an active strategy."""
    rows: list[ResearchRow] = []
    for year in years:
        for symbol in symbols:
            for timeframe in timeframes:
                for preset in presets:
                    rows.append(
                        _run_one(
                            data_root=data_root,
                            symbol=symbol,
                            timeframe=timeframe,
                            year=year,
                            preset=preset,
                        )
                    )
    return rows


def evaluate_research_gate(
    metrics: dict[str, float],
    *,
    positive_windows: int,
) -> tuple[bool, tuple[str, ...]]:
    """Apply existing gates plus the fixed stricter candidate gates."""
    passed, inherited_reasons = validate_strategies.evaluate_thresholds(metrics)
    reasons = list(inherited_reasons)
    if metrics['profit_factor'] < 1.15:
        reasons.append('cost-after Profit Factor is below 1.15')
    if positive_windows < 8:
        reasons.append('fewer than 8 of 12 independent windows are positive')
    return passed and not reasons, tuple(reasons)


def write_report(rows: Sequence[ResearchRow], output_path: Path) -> None:
    """Write the per-slice research record; it never promotes a strategy."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# PULLBACK_CONFIRMATION Research Report',
        '',
        '- Candidate status: research only; not eligible for web, testnet, or live use.',
        '- Costs: taker 0.0005, slippage 0.0002, funding 0.0001 per 8 hours.',
        '- State machine and promotion rules: `docs/research/pullback-confirmation-design.md`.',
        '',
        '| Symbol | Timeframe | Year | 4h Preset | Status | Avg 30d % | Positive Windows | Annual % | Max DD % | PF | Trades | Reasons |',
        '|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        lines.append(
            '| '
            f'{row.symbol} | {row.timeframe} | {row.year} | {row.preset.value} | '
            f'{row.status} | {_number(row.avg_window_return_pct)} | '
            f'{_integer(row.positive_windows)} | {_number(row.annual_return_pct)} | '
            f'{_number(row.max_drawdown_pct)} | {_number(row.profit_factor)} | '
            f'{_integer(row.annual_trades)} | {"; ".join(row.reasons) or "-"} |'
        )
    lines.append('')
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def _run_one(
    *,
    data_root: Path,
    symbol: str,
    timeframe: str,
    year: int,
    preset: PullbackFilterPreset,
) -> ResearchRow:
    try:
        engine, end_time = _research_engine_and_end_time(
            data_root=data_root,
            symbol=symbol,
            timeframe=timeframe,
            year=year,
        )
        windows = validate_strategies._non_overlapping_windows(
            end_time=end_time,
            count=validate_strategies.WINDOW_COUNT,
            days=validate_strategies.WINDOW_DAYS,
            timeframe=timeframe,
        )
        parameters = SignalParameters(pullback_filter_preset=preset)
        window_results = [
            _run_backtest(
                engine,
                symbol=symbol,
                timeframe=timeframe,
                parameters=parameters,
                start=start,
                end=end,
                days=validate_strategies.WINDOW_DAYS,
            )
            for start, end in windows
        ]
        annual_start = (
            end_time
            - pd.Timedelta(days=validate_strategies.ANNUAL_DAYS)
            + validate_strategies._timeframe_delta(timeframe)
        )
        annual_result = _run_backtest(
            engine,
            symbol=symbol,
            timeframe=timeframe,
            parameters=parameters,
            start=annual_start,
            end=end_time,
            days=validate_strategies.ANNUAL_DAYS,
        )
        metrics = validate_strategies._metrics(window_results, annual_result)
        positive_windows = sum(
            result.total_return_pct > 0 for result in window_results
        )
        passed, reasons = evaluate_research_gate(
            metrics,
            positive_windows=positive_windows,
        )
        return ResearchRow(
            symbol=symbol,
            timeframe=timeframe,
            year=year,
            preset=preset,
            status='PASS_SLICE' if passed else 'FAIL_SLICE',
            reasons=reasons,
            avg_window_return_pct=metrics['avg_window_return_pct'],
            positive_windows=positive_windows,
            annual_return_pct=metrics['annual_return_pct'],
            max_drawdown_pct=metrics['max_drawdown_pct'],
            profit_factor=metrics['profit_factor'],
            annual_trades=int(metrics['annual_trades']),
        )
    except (FileNotFoundError, ValueError) as exc:
        return ResearchRow(
            symbol=symbol,
            timeframe=timeframe,
            year=year,
            preset=preset,
            status='DATA_INSUFFICIENT',
            reasons=(str(exc),),
        )


def _research_engine_and_end_time(
    *,
    data_root: Path,
    symbol: str,
    timeframe: str,
    year: int,
) -> tuple[BacktestEngine, pd.Timestamp]:
    safe_symbol = symbol.replace('/', '_')
    yearly_dir = data_root / str(year)
    yearly_entry_path = yearly_dir / f'{safe_symbol}_{timeframe}.csv'
    yearly_engine = BacktestEngine(data_dir=yearly_dir)
    yearly_entry = yearly_engine.load_data(yearly_entry_path)
    if yearly_entry.empty:
        raise ValueError(f'{symbol} {timeframe} {year} data is empty')

    end_time = validate_strategies._as_utc_timestamp(yearly_entry.index.max())
    annual_start = (
        end_time
        - pd.Timedelta(days=validate_strategies.ANNUAL_DAYS)
        + validate_strategies._timeframe_delta(timeframe)
    )
    yearly_start = validate_strategies._as_utc_timestamp(yearly_entry.index.min())
    if yearly_start > annual_start:
        raise ValueError(
            f'{symbol} {timeframe} {year} does not contain a full 365-day slice'
        )

    merged_dir = validate_strategies._materialize_validation_data_dir(
        data_root,
        symbol=symbol,
        timeframe=timeframe,
    )
    engine = BacktestEngine(data_dir=merged_dir)
    warmup_start = annual_start - validate_strategies._warmup_duration(timeframe)
    for required_timeframe in (timeframe, '1h', '4h'):
        path = merged_dir / f'{safe_symbol}_{required_timeframe}.csv'
        frame = engine.load_data(path)
        if frame.empty:
            raise ValueError(f'{symbol} {required_timeframe} merged data is empty')
        actual_start = validate_strategies._as_utc_timestamp(frame.index.min())
        if actual_start > warmup_start:
            raise ValueError(
                f'{symbol} {required_timeframe} lacks warmup before {year}'
            )
    return engine, end_time


def _run_backtest(
    engine: BacktestEngine,
    *,
    symbol: str,
    timeframe: str,
    parameters: SignalParameters,
    start: object,
    end: object,
    days: int,
) -> BacktestResult:
    return engine.run_signal_mode(
        symbol=symbol,
        timeframe=timeframe,
        mode=RESEARCH_MODE,
        backtest_days=days,
        window_start=start,
        window_end=end,
        cash=100,
        opening_amount=10,
        margin_mode=MarginMode.ISOLATED,
        leverage=5,
        taker_fee=validate_strategies.VALIDATION_TAKER_FEE,
        slippage_rate=validate_strategies.VALIDATION_SLIPPAGE_RATE,
        funding_rate=validate_strategies.VALIDATION_FUNDING_RATE,
        signal_parameters=parameters,
        save_result=False,
    )


def _number(value: float | None) -> str:
    return '-' if value is None else f'{value:.2f}'


def _integer(value: int | None) -> str:
    return '-' if value is None else str(value)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run fixed pullback candidate research.')
    parser.add_argument(
        '--output',
        type=Path,
        default=PROJECT_ROOT / 'docs' / 'research' / 'pullback-confirmation-report.md',
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = _parse_args()
    rows = run_research_matrix()
    write_report(rows, args.output)
    failed = sum(row.status != 'PASS_SLICE' for row in rows)
    logger.info('rows=%s failed=%s output=%s', len(rows), failed, args.output)


if __name__ == '__main__':
    main()
