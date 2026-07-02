from __future__ import annotations

from collections.abc import Callable
from math import isfinite
from typing import Literal, cast

import pandas as pd

from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.signal_models import (
    MarginMode,
    MarketSnapshot,
    Signal,
    SignalMode,
    SimulationResult,
    SimulationTrade,
    TradePlan,
)

SignalDispatcher = Callable[[MarketSnapshot, SignalMode], Signal | None]
ExitReason = Literal['STOP', 'TARGET', 'LIQUIDATION', 'FINALIZE']
ExitPhase = Literal['GAP', 'INTRABAR']


def liquidation_price(
    side: Literal['BUY', 'SELL'] | str,
    fill_price: float,
    leverage: float,
    opening_amount: float,
    account_balance: float,
    margin_mode: MarginMode,
    maintenance_margin_rate: float,
) -> float:
    """Return the linear USDT perpetual liquidation price for one position."""
    _positive('fill_price', fill_price)
    _positive('leverage', leverage)
    _positive('opening_amount', opening_amount)
    _positive('account_balance', account_balance)
    _rate('maintenance_margin_rate', maintenance_margin_rate, upper_bound=1)
    if side not in {'BUY', 'SELL'}:
        raise ValueError('side must be BUY or SELL')
    if not isinstance(margin_mode, MarginMode):
        raise ValueError('margin_mode must be ISOLATED or CROSS')

    quantity = opening_amount * leverage / fill_price
    collateral = opening_amount if margin_mode is MarginMode.ISOLATED else account_balance
    if side == 'BUY':
        return max(
            0.0,
            (quantity * fill_price - collateral)
            / (quantity * (1 - maintenance_margin_rate)),
        )
    return (collateral + quantity * fill_price) / (
        quantity * (1 + maintenance_margin_rate)
    )


def commission(notional: float, taker_fee: float) -> float:
    return abs(notional) * taker_fee


def funding_cash_flow(side: Literal['BUY', 'SELL'] | str, notional: float, rate: float) -> float:
    if side not in {'BUY', 'SELL'}:
        raise ValueError('side must be BUY or SELL')
    return -notional * rate if side == 'BUY' else notional * rate


def build_trade_plan(
    signal: Signal,
    *,
    fill_price: float,
    account_balance: float,
    opening_amount: float,
    leverage: float,
    margin_mode: MarginMode,
    fill_time: pd.Timestamp | None = None,
    maintenance_margin_rate: float = 0.005,
) -> TradePlan:
    """Price a signal once from its actual fill and frozen signal distances."""
    _positive('fill_price', fill_price)
    _positive('account_balance', account_balance)
    _positive('opening_amount', opening_amount)
    _positive('leverage', leverage)
    if opening_amount > account_balance:
        raise ValueError('opening_amount must not exceed account_balance')
    if not isinstance(signal, Signal):
        raise ValueError('signal must be a Signal')
    if not isinstance(margin_mode, MarginMode):
        raise ValueError('margin_mode must be ISOLATED or CROSS')
    _positive('signal.atr_snapshot', signal.atr_snapshot)
    _positive('signal.stop_distance', signal.stop_distance)
    _positive('signal.target_distance', signal.target_distance)
    _rate('maintenance_margin_rate', maintenance_margin_rate, upper_bound=1)

    actual_fill_time = signal.signal_time if fill_time is None else _aware_timestamp(
        'fill_time', fill_time
    )
    notional = opening_amount * leverage
    quantity = notional / fill_price
    direction = 1 if signal.side == 'BUY' else -1
    return TradePlan(
        signal=signal,
        fill_time=actual_fill_time,
        fill_price=float(fill_price),
        atr_snapshot=signal.atr_snapshot,
        quantity=quantity,
        opening_amount=float(opening_amount),
        notional_amount=notional,
        leverage=float(leverage),
        margin_mode=margin_mode,
        stop_price=fill_price - direction * signal.stop_distance,
        target_price=fill_price + direction * signal.target_distance,
        expected_stop_amount=round(quantity * signal.stop_distance, 8),
        expected_target_amount=round(quantity * signal.target_distance, 8),
        liquidation_price=liquidation_price(
            signal.side,
            fill_price,
            leverage,
            opening_amount,
            account_balance,
            margin_mode,
            maintenance_margin_rate,
        ),
    )


class SignalSimulator:
    def __init__(self, dispatcher: SignalDispatcher = dispatch_signal) -> None:
        self._dispatcher = dispatcher

    def run(
        self,
        snapshots: pd.Series,
        mode: SignalMode,
        cash: float,
        opening_amount: float,
        leverage: float,
        margin_mode: MarginMode,
        taker_fee: float,
        slippage_rate: float,
        funding_rate: float,
        maintenance_margin_rate: float,
    ) -> SimulationResult:
        _validate_run_inputs(
            snapshots,
            mode=mode,
            cash=cash,
            opening_amount=opening_amount,
            leverage=leverage,
            margin_mode=margin_mode,
            taker_fee=taker_fee,
            slippage_rate=slippage_rate,
            funding_rate=funding_rate,
            maintenance_margin_rate=maintenance_margin_rate,
        )
        if snapshots.empty:
            return SimulationResult((), pd.Series(dtype=float, name='equity'), 0)

        account_cash = float(cash)
        pending: Signal | None = None
        position: TradePlan | None = None
        position_entry_commission = 0.0
        position_funding = 0.0
        funding_cursor: pd.Timestamp | None = None
        trades: list[SimulationTrade] = []
        equity_values: list[float] = []
        equity_index: list[pd.Timestamp] = []
        maximum_concurrent_positions = 0

        for snapshot in snapshots:
            timestamp = snapshot.closed_at
            if pending is not None:
                fill_price = _adverse_price(pending.side, snapshot.open, slippage_rate)
                position_entry_commission = commission(
                    opening_amount * leverage,
                    taker_fee,
                )
                if opening_amount + position_entry_commission > account_cash:
                    pending = None
                    break
                account_cash -= position_entry_commission
                position = build_trade_plan(
                    pending,
                    fill_time=snapshot.opened_at,
                    fill_price=fill_price,
                    account_balance=account_cash,
                    opening_amount=opening_amount,
                    leverage=leverage,
                    margin_mode=margin_mode,
                    maintenance_margin_rate=maintenance_margin_rate,
                )
                position_funding = 0.0
                funding_cursor = snapshot.opened_at
                pending = None
                maximum_concurrent_positions = max(maximum_concurrent_positions, 1)

            if position is not None:
                assert funding_cursor is not None
                funding_before_open = _settle_funding(
                    position,
                    funding_cursor,
                    snapshot.opened_at,
                    funding_rate,
                    include_end=False,
                )
                account_cash += funding_before_open
                position_funding += funding_before_open
                effective_liquidation_price: float | None = None
                current_liquidation_price = _current_liquidation_price(
                    position,
                    account_cash,
                    maintenance_margin_rate,
                )
                exit_details = _exit_for_snapshot(
                    position,
                    snapshot,
                    slippage_rate,
                    current_liquidation_price,
                    phase='GAP',
                )
                if (
                    exit_details is not None
                    and exit_details[1] == 'LIQUIDATION'
                    and position.margin_mode is MarginMode.CROSS
                ):
                    effective_liquidation_price = current_liquidation_price
                if exit_details is not None:
                    exit_price, reason = exit_details
                    trade, account_cash = _close_trade(
                        position,
                        exit_time=snapshot.opened_at,
                        exit_price=exit_price,
                        exit_reason=reason,
                        account_cash=account_cash,
                        entry_commission=position_entry_commission,
                        funding=position_funding,
                        taker_fee=taker_fee,
                        effective_liquidation_price=effective_liquidation_price,
                    )
                    trades.append(trade)
                    position = None
                    funding_cursor = None
                else:
                    funding_before_close = _settle_funding(
                        position,
                        funding_cursor,
                        snapshot.closed_at,
                        funding_rate,
                        include_end=False,
                    )
                    intrabar_funding = funding_before_close - funding_before_open
                    account_cash += intrabar_funding
                    position_funding += intrabar_funding
                    current_liquidation_price = _current_liquidation_price(
                        position,
                        account_cash,
                        maintenance_margin_rate,
                    )
                    exit_details = _exit_for_snapshot(
                        position,
                        snapshot,
                        slippage_rate,
                        current_liquidation_price,
                        phase='INTRABAR',
                    )
                    if (
                        exit_details is not None
                        and exit_details[1] == 'LIQUIDATION'
                        and position.margin_mode is MarginMode.CROSS
                    ):
                        effective_liquidation_price = current_liquidation_price

                if position is not None and exit_details is not None:
                    exit_price, reason = exit_details
                    trade, account_cash = _close_trade(
                        position,
                        exit_time=snapshot.closed_at,
                        exit_price=exit_price,
                        exit_reason=reason,
                        account_cash=account_cash,
                        entry_commission=position_entry_commission,
                        funding=position_funding,
                        taker_fee=taker_fee,
                        effective_liquidation_price=effective_liquidation_price,
                    )
                    trades.append(trade)
                    position = None
                    funding_cursor = None
                elif position is not None:
                    funding_through_close = _settle_funding(
                        position,
                        funding_cursor,
                        snapshot.closed_at,
                        funding_rate,
                        include_end=True,
                    )
                    closing_boundary_funding = (
                        funding_through_close - funding_before_close
                    )
                    account_cash += closing_boundary_funding
                    position_funding += closing_boundary_funding
                    funding_cursor = snapshot.closed_at
                    if position.margin_mode is MarginMode.CROSS:
                        current_liquidation_price = _current_liquidation_price(
                            position,
                            account_cash,
                            maintenance_margin_rate,
                        )
                        close_crossed_liquidation = (
                            position.signal.side == 'BUY'
                            and snapshot.close <= current_liquidation_price
                        ) or (
                            position.signal.side == 'SELL'
                            and snapshot.close >= current_liquidation_price
                        )
                        if close_crossed_liquidation:
                            exit_price = _adverse_exit_price(
                                position.signal.side,
                                snapshot.close,
                                slippage_rate,
                            )
                            trade, account_cash = _close_trade(
                                position,
                                exit_time=snapshot.closed_at,
                                exit_price=exit_price,
                                exit_reason='LIQUIDATION',
                                account_cash=account_cash,
                                entry_commission=position_entry_commission,
                                funding=position_funding,
                                taker_fee=taker_fee,
                                effective_liquidation_price=(
                                    current_liquidation_price
                                ),
                            )
                            trades.append(trade)
                            position = None
                            funding_cursor = None

            equity = account_cash
            if position is not None:
                equity += _gross_pnl(position, snapshot.close)
            equity_values.append(equity)
            equity_index.append(timestamp)
            if equity <= 0:
                if position is not None:
                    exit_price = _adverse_exit_price(
                        position.signal.side, snapshot.close, slippage_rate
                    )
                    trade, account_cash = _close_trade(
                        position,
                        exit_time=timestamp,
                        exit_price=exit_price,
                        exit_reason='LIQUIDATION',
                        account_cash=account_cash,
                        entry_commission=position_entry_commission,
                        funding=position_funding,
                        taker_fee=taker_fee,
                        effective_liquidation_price=(
                            _current_liquidation_price(
                                position,
                                account_cash,
                                maintenance_margin_rate,
                            )
                            if position.margin_mode is MarginMode.CROSS
                            else position.liquidation_price
                        ),
                    )
                    trades.append(trade)
                    position = None
                    equity_values[-1] = account_cash
                break

            if position is None and pending is None:
                pending = self._dispatcher(snapshot, mode)

        if position is not None:
            final_snapshot = cast(MarketSnapshot, snapshots.iloc[-1])
            exit_price = _adverse_exit_price(
                position.signal.side,
                final_snapshot.close,
                slippage_rate,
            )
            trade, account_cash = _close_trade(
                position,
                exit_time=final_snapshot.closed_at,
                exit_price=exit_price,
                exit_reason='FINALIZE',
                account_cash=account_cash,
                entry_commission=position_entry_commission,
                funding=position_funding,
                taker_fee=taker_fee,
            )
            trades.append(trade)
            equity_values[-1] = account_cash

        equity_curve = pd.Series(
            equity_values,
            index=pd.DatetimeIndex(equity_index),
            dtype=float,
            name='equity',
        )
        return SimulationResult(tuple(trades), equity_curve, maximum_concurrent_positions)


def _exit_for_snapshot(
    plan: TradePlan,
    snapshot: MarketSnapshot,
    slippage_rate: float,
    current_liquidation_price: float,
    *,
    phase: ExitPhase,
) -> tuple[float, ExitReason] | None:
    side = plan.signal.side
    if phase == 'GAP' and side == 'BUY':
        if snapshot.open <= current_liquidation_price:
            return (
                _adverse_exit_price(side, snapshot.open, slippage_rate),
                'LIQUIDATION',
            )
        if snapshot.open <= plan.stop_price:
            return _adverse_exit_price(side, snapshot.open, slippage_rate), 'STOP'
        if snapshot.open >= plan.target_price:
            return plan.target_price, 'TARGET'
    elif phase == 'INTRABAR' and side == 'BUY':
        adverse_price = max(plan.stop_price, current_liquidation_price)
        if snapshot.low <= adverse_price:
            reason: ExitReason = (
                'LIQUIDATION'
                if adverse_price == current_liquidation_price
                else 'STOP'
            )
            return adverse_price, reason
        if snapshot.high >= plan.target_price:
            return plan.target_price, 'TARGET'
    elif phase == 'GAP':
        if snapshot.open >= current_liquidation_price:
            return (
                _adverse_exit_price(side, snapshot.open, slippage_rate),
                'LIQUIDATION',
            )
        if snapshot.open >= plan.stop_price:
            return _adverse_exit_price(side, snapshot.open, slippage_rate), 'STOP'
        if snapshot.open <= plan.target_price:
            return plan.target_price, 'TARGET'
    else:
        adverse_price = min(plan.stop_price, current_liquidation_price)
        if snapshot.high >= adverse_price:
            reason = (
                'LIQUIDATION'
                if adverse_price == current_liquidation_price
                else 'STOP'
            )
            return adverse_price, reason
        if snapshot.low <= plan.target_price:
            return plan.target_price, 'TARGET'
    return None


def _close_trade(
    plan: TradePlan,
    *,
    exit_time: pd.Timestamp,
    exit_price: float,
    exit_reason: ExitReason,
    account_cash: float,
    entry_commission: float,
    funding: float,
    taker_fee: float,
    effective_liquidation_price: float | None = None,
) -> tuple[SimulationTrade, float]:
    gross_pnl = _gross_pnl(plan, exit_price)
    exit_commission = commission(plan.quantity * exit_price, taker_fee)
    pnl = gross_pnl - entry_commission - exit_commission + funding
    account_cash += gross_pnl - exit_commission
    trade = SimulationTrade(
        signal=plan.signal,
        fill_time=plan.fill_time,
        fill_price=plan.fill_price,
        atr_snapshot=plan.atr_snapshot,
        quantity=plan.quantity,
        opening_amount=plan.opening_amount,
        notional_amount=plan.notional_amount,
        leverage=plan.leverage,
        margin_mode=plan.margin_mode,
        stop_price=plan.stop_price,
        target_price=plan.target_price,
        expected_stop_amount=plan.expected_stop_amount,
        expected_target_amount=plan.expected_target_amount,
        liquidation_price=(
            plan.liquidation_price
            if effective_liquidation_price is None
            else effective_liquidation_price
        ),
        exit_time=exit_time,
        exit_price=exit_price,
        exit_reason=exit_reason,
        entry_commission=entry_commission,
        exit_commission=exit_commission,
        funding=funding,
        pnl=pnl,
        pnl_percent=pnl / plan.opening_amount * 100,
        environment_side=plan.signal.environment_side,
        filter_label=plan.signal.filter_label,
    )
    return trade, account_cash


def _gross_pnl(plan: TradePlan, price: float) -> float:
    direction = 1 if plan.signal.side == 'BUY' else -1
    return direction * (price - plan.fill_price) * plan.quantity


def _adverse_price(side: Literal['BUY', 'SELL'], price: float, rate: float) -> float:
    return price * (1 + rate) if side == 'BUY' else price * (1 - rate)


def _adverse_exit_price(side: Literal['BUY', 'SELL'], price: float, rate: float) -> float:
    return price * (1 - rate) if side == 'BUY' else price * (1 + rate)


def _funding_events(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    include_end: bool,
) -> int:
    if end <= start:
        return 0
    period_ns = pd.Timedelta(hours=8).value
    end_value = end.value if include_end else end.value - 1
    return max(0, end_value // period_ns - start.value // period_ns)


def _settle_funding(
    plan: TradePlan,
    start: pd.Timestamp,
    end: pd.Timestamp,
    funding_rate: float,
    *,
    include_end: bool,
) -> float:
    events = _funding_events(start, end, include_end=include_end)
    return events * funding_cash_flow(
        plan.signal.side,
        plan.notional_amount,
        funding_rate,
    )


def _current_liquidation_price(
    plan: TradePlan,
    account_cash: float,
    maintenance_margin_rate: float,
) -> float:
    if plan.margin_mode is MarginMode.ISOLATED:
        return plan.liquidation_price
    quantity = plan.quantity
    if plan.signal.side == 'BUY':
        return max(
            0.0,
            (plan.notional_amount - account_cash)
            / (quantity * (1 - maintenance_margin_rate)),
        )
    return (account_cash + plan.notional_amount) / (
        quantity * (1 + maintenance_margin_rate)
    )


def _validate_run_inputs(
    snapshots: pd.Series,
    *,
    mode: SignalMode,
    cash: float,
    opening_amount: float,
    leverage: float,
    margin_mode: MarginMode,
    taker_fee: float,
    slippage_rate: float,
    funding_rate: float,
    maintenance_margin_rate: float,
) -> None:
    if not isinstance(snapshots, pd.Series):
        raise ValueError('snapshots must be a pandas Series')
    if not isinstance(snapshots.index, pd.DatetimeIndex) or snapshots.index.tz is None:
        raise ValueError('snapshot index must be a timezone-aware DatetimeIndex')
    if snapshots.index.has_duplicates:
        raise ValueError('snapshot index must be unique')
    if not snapshots.index.is_monotonic_increasing:
        raise ValueError('snapshot index must be strictly increasing')
    if not isinstance(mode, SignalMode):
        raise ValueError('mode must be a SignalMode')
    if not isinstance(margin_mode, MarginMode):
        raise ValueError('margin_mode must be ISOLATED or CROSS')
    _positive('cash', cash)
    _positive('opening_amount', opening_amount)
    if opening_amount > cash:
        raise ValueError('opening_amount must not exceed cash')
    _positive('leverage', leverage)
    _rate('taker_fee', taker_fee, upper_bound=1)
    _rate('slippage_rate', slippage_rate, upper_bound=1)
    _rate('funding_rate', funding_rate, upper_bound=1)
    _rate('maintenance_margin_rate', maintenance_margin_rate, upper_bound=1)
    entry_fee = commission(opening_amount * leverage, taker_fee)
    if opening_amount + entry_fee > cash:
        raise ValueError('cash must cover opening_amount and entry fee')

    previous: pd.Timestamp | None = None
    previous_opened_at: pd.Timestamp | None = None
    for index, snapshot in snapshots.items():
        if not isinstance(snapshot, MarketSnapshot):
            raise ValueError('snapshots must contain MarketSnapshot values')
        if pd.Timestamp(index) != snapshot.closed_at:
            raise ValueError('snapshot index must equal each snapshot closed_at')
        if previous is not None and snapshot.closed_at <= previous:
            raise ValueError('snapshot closed_at values must be strictly increasing')
        previous = snapshot.closed_at
        if snapshot.opened_at.tz is None or snapshot.opened_at >= snapshot.closed_at:
            raise ValueError('snapshot opened_at must be timezone-aware and before closed_at')
        if previous_opened_at is not None and snapshot.opened_at <= previous_opened_at:
            raise ValueError('snapshot opened_at values must be strictly increasing')
        previous_opened_at = snapshot.opened_at
        prices = (snapshot.open, snapshot.high, snapshot.low, snapshot.close)
        if not all(isfinite(value) and value > 0 for value in prices):
            raise ValueError('snapshot prices must be finite and positive')
        if (
            snapshot.low > min(snapshot.open, snapshot.close)
            or snapshot.high < max(snapshot.open, snapshot.close)
            or snapshot.low > snapshot.high
        ):
            raise ValueError('snapshot prices must form valid OHLC candles')


def _positive(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be a finite positive number')


def _rate(
    name: str,
    value: float,
    *,
    upper_bound: float,
    inclusive_upper: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f'{name} must be a finite rate')
    valid_upper = value <= upper_bound if inclusive_upper else value < upper_bound
    if value < 0 or not valid_upper:
        raise ValueError(f'{name} must be between 0 and {upper_bound}')


def _aware_timestamp(name: str, value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f'{name} must be timezone-aware')
    return timestamp
