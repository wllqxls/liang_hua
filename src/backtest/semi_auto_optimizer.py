"""Search 2024 order-flow fading candidates for cost-positive human signals."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

import math
import numpy as np
import pandas as pd

from src.research.event_factors import FIXED_ROUND_TRIP_COST
from src.research.order_flow_events import load_funding_year, load_order_flow_year
from src.research.order_flow_failed_push import aggregate_order_flow_to_15m
from src.research.order_flow_fading_push import build_fading_push_candidates


DESIGN_YEAR = 2024
ORDER_FLOW_ROOT = Path('order_flow/binance_um')
TIMEFRAME = '15m'
TAKER_BUY_RATIO_THRESHOLDS = (0.55, 0.575, 0.60)
OI_CHANGE_THRESHOLDS = (0.002, 0.005, 0.01)
HOLDING_WINDOWS = {'30m': 2, '1h': 4, '4h': 16}
EVENT_COOLDOWN_BARS = 4
MINIMUM_EVENTS = 30
MAXIMUM_EVENTS = 100
TARGET_EVENTS = 65
SUPPORTED_SYMBOLS = {'BTC/USDT', 'ETH/USDT'}


@dataclass(frozen=True, slots=True)
class WhiteListItem:
    rank: int
    symbol: str
    mode: str
    timeframe: str
    design_year: int
    taker_buy_ratio_threshold: float
    oi_change_45m_threshold: float
    holding_window: str
    events: int
    average_gross_return: float
    average_round_trip_cost: float
    average_funding_return: float
    average_net_return: float
    net_wins: int
    net_losses: int
    visual_score: float
    sample_score: float
    trigger_logic: str


@dataclass(frozen=True, slots=True)
class WhiteListValidation:
    symbol: str
    validation_year: int
    taker_buy_ratio_threshold: float
    oi_change_45m_threshold: float
    holding_window: str
    events: int
    average_gross_return: float
    average_round_trip_cost: float
    average_funding_return: float
    average_net_return: float
    net_wins: int
    net_losses: int
    net_win_rate: float
    median_net_return: float
    profit_factor: float | None
    top_3_net_share: float | None
    passed: bool
    status: str


@dataclass(frozen=True, slots=True)
class GridExplorationItem:
    """One explicitly non-validating row from a 2025 parameter-grid scan."""

    rank: int
    symbol: str
    exploration_year: int
    taker_buy_ratio_threshold: float
    oi_change_45m_threshold: float
    holding_window: str
    events: int
    net_wins: int
    net_losses: int
    average_gross_return: float
    average_round_trip_cost: float
    average_funding_return: float
    average_net_return: float
    median_net_return: float
    profit_factor: float | None
    passes_numeric_gate: bool
    research_status: str


def build_semi_auto_whitelist(
    data_root: Path,
    *,
    symbol: str,
) -> list[WhiteListItem]:
    """Search the frozen 27-combination 2024 order-flow design grid."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError('order-flow whitelist only supports BTC/USDT and ETH/USDT')
    archive_symbol = symbol.replace('/', '')
    order_flow_root = Path(data_root) / ORDER_FLOW_ROOT
    five_minute = load_order_flow_year(
        order_flow_root,
        symbol=archive_symbol,
        year=DESIGN_YEAR,
    )
    funding_rates = _normalize_funding_rates(load_funding_year(
        order_flow_root,
        symbol=archive_symbol,
        year=DESIGN_YEAR,
    ))
    if funding_rates.empty:
        raise FileNotFoundError(f'{archive_symbol} {DESIGN_YEAR} fundingRate is empty')
    fifteen_minute = aggregate_order_flow_to_15m(five_minute)

    rows: list[WhiteListItem] = []
    for taker_threshold in TAKER_BUY_RATIO_THRESHOLDS:
        for oi_threshold in OI_CHANGE_THRESHOLDS:
            events, _, _ = build_fading_push_candidates(
                fifteen_minute,
                funding_rate=funding_rates,
                taker_buy_ratio_threshold=taker_threshold,
                oi_change_threshold=oi_threshold,
                event_cooldown_bars=EVENT_COOLDOWN_BARS,
            )
            for holding_window, holding_bars in HOLDING_WINDOWS.items():
                metrics = _candidate_metrics(
                    fifteen_minute=fifteen_minute,
                    five_minute=five_minute,
                    funding_rates=funding_rates,
                    events=events,
                    holding_bars=holding_bars,
                )
                if not MINIMUM_EVENTS <= metrics['events'] <= MAXIMUM_EVENTS:
                    continue
                if metrics['average_gross_return'] <= 0 or metrics['average_net_return'] <= 0:
                    continue
                rows.append(WhiteListItem(
                    rank=0,
                    symbol=symbol,
                    mode='ORDER_FLOW_FADING_15M',
                    timeframe=TIMEFRAME,
                    design_year=DESIGN_YEAR,
                    taker_buy_ratio_threshold=taker_threshold,
                    oi_change_45m_threshold=oi_threshold,
                    holding_window=holding_window,
                    events=int(metrics['events']),
                    average_gross_return=metrics['average_gross_return'],
                    average_round_trip_cost=FIXED_ROUND_TRIP_COST,
                    average_funding_return=metrics['average_funding_return'],
                    average_net_return=metrics['average_net_return'],
                    net_wins=int(metrics['net_wins']),
                    net_losses=int(metrics['net_losses']),
                    visual_score=metrics['visual_score'],
                    sample_score=_sample_score(int(metrics['events'])),
                    trigger_logic=(
                        f'15m 主动买入占比≥{taker_threshold * 100:g}%，'
                        f'45分钟 OI 增长≥{oi_threshold * 100:g}%，收盘走弱后做空，'
                        f'持有 {holding_window}'
                    ),
                ))
    rows.sort(
        key=lambda item: (
            item.average_net_return,
            item.sample_score,
            item.visual_score,
            item.average_gross_return,
        ),
        reverse=True,
    )
    return [replace(item, rank=index) for index, item in enumerate(rows[:5], start=1)]


def validate_semi_auto_candidate(
    data_root: Path,
    *,
    symbol: str,
    taker_buy_ratio_threshold: float,
    oi_change_45m_threshold: float,
    holding_window: str,
) -> WhiteListValidation:
    """Evaluate one frozen 2024 candidate on the 2025 joint-screening year."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError('order-flow whitelist only supports BTC/USDT and ETH/USDT')
    if taker_buy_ratio_threshold not in TAKER_BUY_RATIO_THRESHOLDS:
        raise ValueError('taker threshold is outside the frozen 2024 grid')
    if oi_change_45m_threshold not in OI_CHANGE_THRESHOLDS:
        raise ValueError('OI threshold is outside the frozen 2024 grid')
    if holding_window not in HOLDING_WINDOWS:
        raise ValueError('holding window is outside the frozen 2024 grid')
    archive_symbol = symbol.replace('/', '')
    order_flow_root = Path(data_root) / ORDER_FLOW_ROOT
    five_minute = load_order_flow_year(order_flow_root, symbol=archive_symbol, year=2025)
    funding_rates = _normalize_funding_rates(
        load_funding_year(order_flow_root, symbol=archive_symbol, year=2025),
    )
    if funding_rates.empty:
        raise FileNotFoundError(f'{archive_symbol} 2025 fundingRate is empty')
    fifteen_minute = aggregate_order_flow_to_15m(five_minute)
    events, _, _ = build_fading_push_candidates(
        fifteen_minute,
        funding_rate=funding_rates,
        taker_buy_ratio_threshold=taker_buy_ratio_threshold,
        oi_change_threshold=oi_change_45m_threshold,
        event_cooldown_bars=EVENT_COOLDOWN_BARS,
    )
    metrics = _candidate_metrics(
        fifteen_minute=fifteen_minute,
        five_minute=five_minute,
        funding_rates=funding_rates,
        events=events,
        holding_bars=HOLDING_WINDOWS[holding_window],
    )
    passed = bool(
        MINIMUM_EVENTS <= metrics['events'] <= MAXIMUM_EVENTS
        and metrics['average_gross_return'] > 0
        and metrics['average_net_return'] > 0
    )
    return WhiteListValidation(
        symbol=symbol,
        validation_year=2025,
        taker_buy_ratio_threshold=taker_buy_ratio_threshold,
        oi_change_45m_threshold=oi_change_45m_threshold,
        holding_window=holding_window,
        events=int(metrics['events']),
        average_gross_return=float(metrics['average_gross_return']),
        average_round_trip_cost=FIXED_ROUND_TRIP_COST,
        average_funding_return=float(metrics['average_funding_return']),
        average_net_return=float(metrics['average_net_return']),
        net_wins=int(metrics['net_wins']),
        net_losses=int(metrics['net_losses']),
        net_win_rate=float(metrics['net_win_rate']),
        median_net_return=float(metrics['median_net_return']),
        profit_factor=metrics['profit_factor'],
        top_3_net_share=metrics['top_3_net_share'],
        passed=passed,
        status='PASSED' if passed else 'FAILED',
    )


def write_semi_auto_whitelist(items: list[WhiteListItem], destination: Path) -> None:
    """Write the compact 2024 order-flow whitelist CSV, including an empty result."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        'rank', 'symbol', 'mode', 'timeframe', 'design_year',
        'taker_buy_ratio_threshold', 'oi_change_45m_threshold', 'holding_window',
        'events', 'average_gross_return', 'average_round_trip_cost',
        'average_funding_return', 'average_net_return', 'net_wins', 'net_losses', 'visual_score',
        'sample_score', 'trigger_logic',
    ]
    pd.DataFrame([asdict(item) for item in items], columns=columns).to_csv(
        destination,
        index=False,
        encoding='utf-8-sig',
        lineterminator='\n',
    )


def write_semi_auto_validation(
    validation: WhiteListValidation,
    destination: Path,
) -> None:
    """Persist the 2025 joint-screen result beside its exact 2024 candidate."""
    if not destination.exists():
        raise FileNotFoundError('semi-auto whitelist CSV does not exist')
    frame = pd.read_csv(destination, encoding='utf-8-sig')
    match = (
        frame['symbol'].eq(validation.symbol)
        & frame['taker_buy_ratio_threshold'].astype(float).eq(
            validation.taker_buy_ratio_threshold,
        )
        & frame['oi_change_45m_threshold'].astype(float).eq(
            validation.oi_change_45m_threshold,
        )
        & frame['holding_window'].eq(validation.holding_window)
    )
    if int(match.sum()) != 1:
        raise ValueError('frozen whitelist candidate was not found exactly once')
    values = asdict(validation)
    for key, value in values.items():
        if key in {
            'symbol', 'taker_buy_ratio_threshold', 'oi_change_45m_threshold',
            'holding_window',
        }:
            continue
        column = key if key == 'validation_year' else f'validation_{key}'
        frame.loc[match, column] = value
    frame.to_csv(
        destination,
        index=False,
        encoding='utf-8-sig',
        lineterminator='\n',
    )


def is_validation_passed_profile(
    destination: Path,
    *,
    symbol: str,
    taker_buy_ratio_threshold: float,
    oi_change_45m_threshold: float,
    holding_window: str,
) -> bool:
    """Return whether the exact profile passed the persisted two-year screen."""
    if not destination.exists():
        return False
    frame = pd.read_csv(destination, encoding='utf-8-sig')
    required = {
        'symbol', 'taker_buy_ratio_threshold', 'oi_change_45m_threshold',
        'holding_window', 'validation_passed',
    }
    if not required <= set(frame.columns):
        return False
    match = (
        frame['symbol'].eq(symbol)
        & frame['taker_buy_ratio_threshold'].astype(float).eq(taker_buy_ratio_threshold)
        & frame['oi_change_45m_threshold'].astype(float).eq(oi_change_45m_threshold)
        & frame['holding_window'].eq(holding_window)
        & frame['validation_passed'].astype(str).str.lower().eq('true')
    )
    return int(match.sum()) == 1


def explore_2025_parameter_grid(
    data_root: Path,
    *,
    symbol: str,
    excluded_profile: tuple[float, float, str] | None = None,
) -> list[GridExplorationItem]:
    """Scan 2025 as an exploration set; rows must never become validations."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError('order-flow exploration only supports BTC/USDT and ETH/USDT')
    archive_symbol = symbol.replace('/', '')
    order_flow_root = Path(data_root) / ORDER_FLOW_ROOT
    five_minute = load_order_flow_year(order_flow_root, symbol=archive_symbol, year=2025)
    funding_rates = _normalize_funding_rates(
        load_funding_year(order_flow_root, symbol=archive_symbol, year=2025),
    )
    if funding_rates.empty:
        raise FileNotFoundError(f'{archive_symbol} 2025 fundingRate is empty')
    fifteen_minute = aggregate_order_flow_to_15m(five_minute)
    rows: list[GridExplorationItem] = []
    for taker_threshold in TAKER_BUY_RATIO_THRESHOLDS:
        for oi_threshold in OI_CHANGE_THRESHOLDS:
            events, _, _ = build_fading_push_candidates(
                fifteen_minute,
                funding_rate=funding_rates,
                taker_buy_ratio_threshold=taker_threshold,
                oi_change_threshold=oi_threshold,
                event_cooldown_bars=EVENT_COOLDOWN_BARS,
            )
            for holding_window, holding_bars in HOLDING_WINDOWS.items():
                profile = (taker_threshold, oi_threshold, holding_window)
                if excluded_profile is not None and profile == excluded_profile:
                    continue
                metrics = _candidate_metrics(
                    fifteen_minute=fifteen_minute,
                    five_minute=five_minute,
                    funding_rates=funding_rates,
                    events=events,
                    holding_bars=holding_bars,
                )
                passes_gate = bool(
                    MINIMUM_EVENTS <= metrics['events'] <= MAXIMUM_EVENTS
                    and metrics['average_gross_return'] > 0
                    and metrics['average_net_return'] > 0
                )
                rows.append(GridExplorationItem(
                    rank=0,
                    symbol=symbol,
                    exploration_year=2025,
                    taker_buy_ratio_threshold=taker_threshold,
                    oi_change_45m_threshold=oi_threshold,
                    holding_window=holding_window,
                    events=int(metrics['events']),
                    net_wins=int(metrics['net_wins']),
                    net_losses=int(metrics['net_losses']),
                    average_gross_return=float(metrics['average_gross_return']),
                    average_round_trip_cost=FIXED_ROUND_TRIP_COST,
                    average_funding_return=float(metrics['average_funding_return']),
                    average_net_return=float(metrics['average_net_return']),
                    median_net_return=float(metrics['median_net_return']),
                    profit_factor=metrics['profit_factor'],
                    passes_numeric_gate=passes_gate,
                    research_status='EXPLORATION_ONLY',
                ))
    rows.sort(key=lambda item: item.average_net_return, reverse=True)
    return [replace(item, rank=index) for index, item in enumerate(rows, start=1)]


def write_grid_exploration(
    items: list[GridExplorationItem],
    destination: Path,
) -> None:
    """Write an exploration-only grid without touching whitelist validation state."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(item) for item in items]).to_csv(
        destination,
        index=False,
        encoding='utf-8-sig',
        lineterminator='\n',
    )


def _candidate_metrics(
    *,
    fifteen_minute: pd.DataFrame,
    five_minute: pd.DataFrame,
    funding_rates: pd.Series,
    events: pd.DataFrame,
    holding_bars: int,
) -> dict[str, float | int | None]:
    """Use next-open entry, fixed-window close exit, fixed cost and real funding."""
    gross_returns: list[float] = []
    funding_returns: list[float] = []
    net_returns: list[float] = []
    visual_scores: list[float] = []
    positions = pd.Series(np.arange(len(fifteen_minute)), index=fifteen_minute.index)
    for timestamp, event in events.iterrows():
        event_position = int(positions.loc[timestamp])
        entry_position = event_position + 1
        exit_position = event_position + holding_bars
        if entry_position >= len(fifteen_minute) or exit_position >= len(fifteen_minute):
            continue
        entry_bar = fifteen_minute.iloc[entry_position]
        exit_bar = fifteen_minute.iloc[exit_position]
        entry_time = pd.Timestamp(fifteen_minute.index[entry_position])
        exit_time = pd.Timestamp(fifteen_minute.index[exit_position]) + pd.Timedelta(minutes=15)
        entry_price = float(entry_bar['open'])
        exit_price = float(exit_bar['close'])
        if not math.isfinite(entry_price) or not math.isfinite(exit_price) or entry_price <= 0:
            raise ValueError('order-flow whitelist encountered an invalid entry or exit price')
        gross = (entry_price - exit_price) / entry_price
        funding = _short_funding_return(
            five_minute=five_minute,
            funding_rates=funding_rates,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=entry_price,
        )
        gross_returns.append(gross)
        funding_returns.append(funding)
        net_returns.append(gross - FIXED_ROUND_TRIP_COST + funding)
        visual_scores.append(_visual_score(event))
    count = len(gross_returns)
    net_array = np.asarray(net_returns, dtype=float)
    net_wins = int((net_array > 0).sum()) if count else 0
    net_losses = count - net_wins
    gains = float(net_array[net_array > 0].sum()) if count else 0.0
    losses = float(-net_array[net_array < 0].sum()) if count else 0.0
    profit_factor = gains / losses if losses > 0 else None
    total_net = float(net_array.sum()) if count else 0.0
    top_3_net_share = (
        float(np.sort(net_array)[-3:].sum() / total_net)
        if count and total_net > 0
        else None
    )
    return {
        'events': count,
        'average_gross_return': float(np.mean(gross_returns)) if count else 0.0,
        'average_funding_return': float(np.mean(funding_returns)) if count else 0.0,
        'average_net_return': float(np.mean(net_returns)) if count else 0.0,
        'visual_score': float(np.mean(visual_scores)) if count else 0.0,
        'net_wins': net_wins,
        'net_losses': net_losses,
        'net_win_rate': float((net_array > 0).mean()) if count else 0.0,
        'median_net_return': float(np.median(net_array)) if count else 0.0,
        'profit_factor': profit_factor,
        'top_3_net_share': top_3_net_share,
    }


def _short_funding_return(
    *,
    five_minute: pd.DataFrame,
    funding_rates: pd.Series,
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    entry_price: float,
) -> float:
    """Return signed funding PnL divided by entry notional for one short trade."""
    due = funding_rates.loc[
        (funding_rates.index > entry_time) & (funding_rates.index <= exit_time)
    ]
    total = 0.0
    for settlement_time, rate in due.items():
        completed = five_minute.loc[
            (five_minute.index + pd.Timedelta(minutes=5)) <= settlement_time,
            'close',
        ]
        reference_price = float(completed.iloc[-1]) if not completed.empty else entry_price
        total += float(rate) * reference_price / entry_price
    return total


def _normalize_funding_rates(rates: pd.Series) -> pd.Series:
    if not isinstance(rates.index, pd.DatetimeIndex):
        raise ValueError('funding rate index must be a DatetimeIndex')
    normalized = rates.copy()
    if normalized.index.tz is None:
        normalized.index = normalized.index.tz_localize('UTC')
    else:
        normalized.index = normalized.index.tz_convert('UTC')
    normalized.index = normalized.index.floor('min')
    if normalized.index.has_duplicates:
        normalized = normalized.groupby(level=0).last()
    return normalized.sort_index().astype(float)


def _visual_score(event: pd.Series) -> float:
    atr = float(event['atr_pct']) * float(event['close'])
    if not math.isfinite(atr) or atr <= 0:
        return 0.0
    open_price = float(event['open'])
    close_price = float(event['close'])
    body = abs(close_price - open_price)
    upper_wick = float(event['high']) - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - float(event['low'])
    return max(body, upper_wick, lower_wick) / atr


def _sample_score(events: int) -> float:
    return max(0.0, 1 - abs(events - TARGET_EVENTS) / (TARGET_EVENTS - MINIMUM_EVENTS))
