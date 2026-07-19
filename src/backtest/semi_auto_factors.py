"""Build the two-symbol, three-year semi-automatic factor catalog."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from src.backtest.semi_auto_optimizer import _candidate_metrics
from src.research.event_factors import FIXED_ROUND_TRIP_COST
from src.research.order_flow_events import load_funding_year, load_order_flow_year
from src.research.order_flow_failed_push import aggregate_order_flow_to_15m
from src.research.order_flow_relative_absorption import (
    FACTOR_ID,
    RELATIVE_QUANTILE,
    ROLLING_WINDOW_BARS,
    build_relative_absorption_candidates,
)


FACTOR_YEARS = (2023, 2024, 2025)
FACTOR_SYMBOLS = ('BTC/USDT', 'ETH/USDT')
ORDER_FLOW_ROOT = Path('order_flow/binance_um')
HOLDING_WINDOW = '4h'
HOLDING_BARS = 16
TRIGGER_LOGIC = '30日双80%分位买压+OI，价格收弱'


@dataclass(frozen=True, slots=True)
class AnnualFactorMetrics:
    year: int
    samples: int
    net_wins: int
    net_losses: int
    average_gross_return: float
    average_round_trip_cost: float
    average_funding_return: float
    average_net_return: float
    median_net_return: float
    profit_factor: float | None


@dataclass(frozen=True, slots=True)
class SemiAutoFactorItem:
    symbol: str
    factor_id: str
    mode: str
    timeframe: str
    holding_window: str
    rolling_window_bars: int
    relative_quantile: float
    trigger_logic: str
    metrics_2023: AnnualFactorMetrics
    metrics_2024: AnnualFactorMetrics
    metrics_2025: AnnualFactorMetrics


def build_semi_auto_factors(data_root: Path) -> list[SemiAutoFactorItem]:
    """Return exactly one frozen relative-absorption row for BTC and ETH."""
    return [_build_symbol_factor(Path(data_root), symbol) for symbol in FACTOR_SYMBOLS]


def _build_symbol_factor(data_root: Path, symbol: str) -> SemiAutoFactorItem:
    annual = {
        year: _annual_metrics(data_root, symbol=symbol, year=year)
        for year in FACTOR_YEARS
    }
    return SemiAutoFactorItem(
        symbol=symbol,
        factor_id=FACTOR_ID,
        mode='ORDER_FLOW_ABSORPTION_15M',
        timeframe='15m',
        holding_window=HOLDING_WINDOW,
        rolling_window_bars=ROLLING_WINDOW_BARS,
        relative_quantile=RELATIVE_QUANTILE,
        trigger_logic=TRIGGER_LOGIC,
        metrics_2023=annual[2023],
        metrics_2024=annual[2024],
        metrics_2025=annual[2025],
    )


def _annual_metrics(data_root: Path, *, symbol: str, year: int) -> AnnualFactorMetrics:
    archive_symbol = symbol.replace('/', '')
    root = data_root / ORDER_FLOW_ROOT
    five_minute = load_order_flow_year(root, symbol=archive_symbol, year=year)
    funding_rates = load_funding_year(root, symbol=archive_symbol, year=year)
    if funding_rates.empty:
        raise FileNotFoundError(f'{archive_symbol} {year} fundingRate is empty')
    fifteen_minute = aggregate_order_flow_to_15m(five_minute)
    events, _, _ = build_relative_absorption_candidates(
        fifteen_minute,
        funding_rate=funding_rates,
    )
    metrics = _candidate_metrics(
        fifteen_minute=fifteen_minute,
        five_minute=five_minute,
        funding_rates=funding_rates,
        events=events,
        holding_bars=HOLDING_BARS,
    )
    return AnnualFactorMetrics(
        year=year,
        samples=int(metrics['events']),
        net_wins=int(metrics['net_wins']),
        net_losses=int(metrics['net_losses']),
        average_gross_return=float(metrics['average_gross_return']),
        average_round_trip_cost=FIXED_ROUND_TRIP_COST,
        average_funding_return=float(metrics['average_funding_return']),
        average_net_return=float(metrics['average_net_return']),
        median_net_return=float(metrics['median_net_return']),
        profit_factor=metrics['profit_factor'],
    )


def write_semi_auto_factors(items: list[SemiAutoFactorItem], destination: Path) -> None:
    """Write a flat, audit-friendly three-year factor catalog."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for item in items:
        row: dict[str, object] = {
            'symbol': item.symbol,
            'factor_id': item.factor_id,
            'mode': item.mode,
            'timeframe': item.timeframe,
            'holding_window': item.holding_window,
            'rolling_window_bars': item.rolling_window_bars,
            'relative_quantile': item.relative_quantile,
            'trigger_logic': item.trigger_logic,
        }
        for metrics in (item.metrics_2023, item.metrics_2024, item.metrics_2025):
            for key, value in asdict(metrics).items():
                if key == 'year':
                    continue
                row[f'{metrics.year}_{key}'] = value
        rows.append(row)
    pd.DataFrame(rows).to_csv(
        destination,
        index=False,
        encoding='utf-8-sig',
        lineterminator='\n',
    )


def is_persisted_experimental_factor(
    destination: Path,
    *,
    symbol: str,
    factor_id: str,
    holding_window: str,
) -> bool:
    """Reject arbitrary profiles that were not generated into the local catalog."""
    if not destination.exists():
        return False
    frame = pd.read_csv(destination, encoding='utf-8-sig')
    required = {'symbol', 'factor_id', 'holding_window'}
    if not required <= set(frame.columns):
        return False
    match = (
        frame['symbol'].eq(symbol)
        & frame['factor_id'].eq(factor_id)
        & frame['holding_window'].eq(holding_window)
    )
    return int(match.sum()) == 1
