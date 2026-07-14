from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class DiagnosticSlice:
    label: str
    trades: int
    win_rate_pct: float
    gross_pnl: float
    commission: float
    funding_cash_flow: float
    net_cost: float
    net_pnl: float
    profit_factor: float
    average_net_pnl: float


@dataclass(frozen=True, slots=True)
class StrategyDiagnostics:
    trades: int
    win_rate_pct: float
    gross_pnl: float
    commission: float
    funding_cash_flow: float
    net_cost: float
    net_pnl: float
    gross_profit_factor: float
    net_profit_factor: float
    average_net_pnl: float
    cost_to_gross_profit_pct: float | None
    by_exit_reason: tuple[DiagnosticSlice, ...]
    by_side: tuple[DiagnosticSlice, ...]
    by_environment_1h: tuple[DiagnosticSlice, ...]
    by_filter_4h: tuple[DiagnosticSlice, ...]


def analyze_trades(
    trades: Sequence[Mapping[str, object]],
) -> StrategyDiagnostics:
    """Summarize one annual trade list without changing execution results."""
    normalized = [_normalize_trade(trade) for trade in trades]
    net_values = [trade['net_pnl'] for trade in normalized]
    gross_values = [trade['gross_pnl'] for trade in normalized]
    commission = sum(trade['commission'] for trade in normalized)
    funding_cash_flow = sum(trade['funding_cash_flow'] for trade in normalized)
    gross_profit = sum(value for value in gross_values if value > 0)
    net_cost = commission - funding_cash_flow
    cost_share = (
        net_cost / gross_profit * 100
        if gross_profit > 0
        else None
    )
    return StrategyDiagnostics(
        trades=len(normalized),
        win_rate_pct=_win_rate(net_values),
        gross_pnl=sum(gross_values),
        commission=commission,
        funding_cash_flow=funding_cash_flow,
        net_cost=net_cost,
        net_pnl=sum(net_values),
        gross_profit_factor=_profit_factor(gross_values),
        net_profit_factor=_profit_factor(net_values),
        average_net_pnl=_average(net_values),
        cost_to_gross_profit_pct=cost_share,
        by_exit_reason=_group_slices(normalized, 'exit_reason'),
        by_side=_group_slices(normalized, 'side'),
        by_environment_1h=_group_slices(normalized, 'environment_1h'),
        by_filter_4h=_group_slices(normalized, 'filter_4h'),
    )


def _normalize_trade(trade: Mapping[str, object]) -> dict[str, float | str]:
    net_pnl = _number(trade.get('pnl'))
    entry_commission = _number(trade.get('entry_commission'))
    exit_commission = _number(trade.get('exit_commission'))
    funding_cash_flow = _number(trade.get('funding_fee'))
    commission = entry_commission + exit_commission
    return {
        'net_pnl': net_pnl,
        'gross_pnl': net_pnl + commission - funding_cash_flow,
        'commission': commission,
        'funding_cash_flow': funding_cash_flow,
        'exit_reason': _label(trade.get('exit_reason')),
        'side': _label(trade.get('side')),
        'environment_1h': _label(trade.get('environment_1h')),
        'filter_4h': _label(trade.get('filter_4h')),
    }


def _group_slices(
    trades: Sequence[Mapping[str, float | str]],
    field: str,
) -> tuple[DiagnosticSlice, ...]:
    labels = sorted({str(trade[field]) for trade in trades})
    slices: list[DiagnosticSlice] = []
    for label in labels:
        group = [trade for trade in trades if trade[field] == label]
        net_values = [float(trade['net_pnl']) for trade in group]
        gross_values = [float(trade['gross_pnl']) for trade in group]
        commission = sum(float(trade['commission']) for trade in group)
        funding_cash_flow = sum(
            float(trade['funding_cash_flow']) for trade in group
        )
        slices.append(
            DiagnosticSlice(
                label=label,
                trades=len(group),
                win_rate_pct=_win_rate(net_values),
                gross_pnl=sum(gross_values),
                commission=commission,
                funding_cash_flow=funding_cash_flow,
                net_cost=commission - funding_cash_flow,
                net_pnl=sum(net_values),
                profit_factor=_profit_factor(net_values),
                average_net_pnl=_average(net_values),
            )
        )
    return tuple(slices)


def _number(value: object) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return number if isfinite(number) else 0.0


def _label(value: object) -> str:
    text = str(value or '').strip()
    return text if text else 'UNKNOWN'


def _win_rate(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(value > 0 for value in values) / len(values) * 100


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _profit_factor(values: Sequence[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = sum(abs(value) for value in values if value < 0)
    if wins <= 0:
        return 0.0
    if losses <= 0:
        return 99.0
    return wins / losses
