from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from src.backtest.signal_simulator import (
    SignalSimulator,
    _current_liquidation_price,
    _exit_for_snapshot,
    build_trade_plan,
    liquidation_price,
)
from src.strategies.signal_models import (
    FilterLabel,
    MarginMode,
    MarketSnapshot,
    Signal,
    SignalMode,
)


def _snapshot(
    closed_at: str,
    *,
    opened_at: str | None = None,
    open_price: float = 100,
    high: float = 101,
    low: float = 99,
    close: float = 100,
) -> MarketSnapshot:
    timestamp = pd.Timestamp(closed_at, tz='UTC')
    return MarketSnapshot(
        opened_at=(
            timestamp - pd.Timedelta(minutes=5)
            if opened_at is None
            else pd.Timestamp(opened_at, tz='UTC')
        ),
        closed_at=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        atr=10,
        rsi=50,
        bollinger_upper=110,
        bollinger_lower=90,
        previous_high_20=105,
        previous_low_20=95,
        environment_side='BUY',
        filter_label=FilterLabel.LONG,
        context_1h_closed_at=timestamp,
        context_4h_closed_at=timestamp,
    )


def _signal(snapshot: MarketSnapshot, side: str = 'BUY') -> Signal:
    direction = 1 if side == 'BUY' else -1
    return Signal(
        mode=SignalMode.KEY_LEVEL,
        strategy='KEY_LEVEL',
        side=side,  # type: ignore[arg-type]
        signal_time=snapshot.closed_at,
        signal_close=snapshot.close,
        atr_snapshot=10,
        stop_atr_multiple=0.6,
        target_atr_multiple=1.2,
        stop_distance=6,
        target_distance=12,
        estimated_stop_price=snapshot.close - direction * 6,
        estimated_target_price=snapshot.close + direction * 12,
        environment_side=side,  # type: ignore[arg-type]
        filter_label=snapshot.filter_label,
        reason='test',
        score=1,
    )


def _series(*snapshots: MarketSnapshot) -> pd.Series:
    return pd.Series(
        snapshots,
        index=pd.DatetimeIndex([snapshot.closed_at for snapshot in snapshots]),
        dtype=object,
    )


def _run(
    snapshots: pd.Series,
    dispatcher,
    **overrides: object,
):
    arguments = {
        'mode': SignalMode.KEY_LEVEL,
        'cash': 100.0,
        'opening_amount': 10.0,
        'leverage': 5.0,
        'margin_mode': MarginMode.ISOLATED,
        'taker_fee': 0.0,
        'slippage_rate': 0.0,
        'funding_rate': 0.0,
        'maintenance_margin_rate': 0.005,
    }
    arguments.update(overrides)
    return SignalSimulator(dispatcher=dispatcher).run(snapshots, **arguments)


def test_trade_plan_uses_actual_fill_and_frozen_signal_distances() -> None:
    snapshot = _snapshot('2026-01-01 00:05')
    signal = _signal(snapshot)

    plan = build_trade_plan(
        signal,
        fill_time=pd.Timestamp('2026-01-01 00:10', tz='UTC'),
        fill_price=2000,
        account_balance=100,
        opening_amount=10,
        leverage=5,
        margin_mode=MarginMode.ISOLATED,
    )

    assert plan.atr_snapshot == signal.atr_snapshot == 10
    assert plan.stop_price == 1994
    assert plan.target_price == 2012
    assert plan.quantity == 0.025
    assert plan.notional_amount == 50
    assert plan.expected_stop_amount == 0.15
    assert plan.expected_target_amount == 0.30


def test_signal_fills_at_next_open_with_adverse_entry_slippage() -> None:
    first = _snapshot('2026-01-01 00:05')
    second = _snapshot('2026-01-01 00:10', open_price=110, high=111, low=109, close=110)
    calls = 0

    def dispatcher(snapshot: MarketSnapshot, mode: SignalMode) -> Signal | None:
        nonlocal calls
        calls += 1
        return _signal(snapshot) if snapshot is first else None

    result = _run(_series(first, second), dispatcher, slippage_rate=0.01)

    trade = result.trades[0]
    assert calls == 1
    assert trade.signal_time == first.closed_at
    assert trade.fill_time == second.opened_at
    assert trade.fill_price == pytest.approx(111.1)
    assert trade.stop_price == pytest.approx(105.1)
    assert trade.exit_reason == 'FINALIZE'
    assert trade.exit_time == second.closed_at


@pytest.mark.parametrize(
    ('side', 'expected_fill', 'expected_stop', 'expected_target'),
    [('BUY', 101, 95, 113), ('SELL', 99, 105, 87)],
)
def test_long_and_short_prices_and_amounts(
    side: str,
    expected_fill: float,
    expected_stop: float,
    expected_target: float,
) -> None:
    first = _snapshot('2026-01-01 00:05')
    second = _snapshot('2026-01-01 00:10', high=102, low=98)

    result = _run(
        _series(first, second),
        lambda snapshot, mode: _signal(snapshot, side) if snapshot is first else None,
        slippage_rate=0.01,
    )

    trade = result.trades[0]
    assert trade.fill_price == expected_fill
    assert trade.stop_price == expected_stop
    assert trade.target_price == expected_target
    assert trade.expected_stop_amount == pytest.approx(50 / expected_fill * 6)
    assert trade.expected_target_amount == pytest.approx(50 / expected_fill * 12)


def test_later_atr_change_does_not_reprice_open_trade() -> None:
    first = _snapshot('2026-01-01 00:05')
    second = replace(_snapshot('2026-01-01 00:10'), atr=1000, high=105, low=95)

    result = _run(
        _series(first, second),
        lambda snapshot, mode: _signal(snapshot) if snapshot is first else None,
    )

    assert result.trades[0].atr_snapshot == 10
    assert result.trades[0].stop_price == 94
    assert result.trades[0].target_price == 112


def test_cross_margin_uses_account_balance_while_isolated_uses_opening_margin() -> None:
    isolated = liquidation_price('BUY', 100, 5, 10, 100, MarginMode.ISOLATED, 0.005)
    cross = liquidation_price('BUY', 100, 5, 10, 100, MarginMode.CROSS, 0.005)
    assert isolated == pytest.approx(80.40201005)
    assert cross == 0
    assert cross < isolated


@pytest.mark.parametrize(
    ('side', 'expected'),
    [
        ('BUY', 110 / 0.995),
        ('SELL', 90 / 1.005),
    ],
)
def test_dynamic_cross_liquidation_formula_accepts_nonpositive_cash(
    side: str,
    expected: float,
) -> None:
    snapshot = _snapshot('2026-01-01 00:05')
    plan = build_trade_plan(
        _signal(snapshot, side),
        fill_price=100,
        account_balance=100,
        opening_amount=10,
        leverage=10,
        margin_mode=MarginMode.CROSS,
    )
    assert _current_liquidation_price(plan, -10, 0.005) == pytest.approx(expected)


@pytest.mark.parametrize(
    ('side', 'margin_mode', 'open_price', 'high', 'low', 'expected_price'),
    [
        ('BUY', MarginMode.ISOLATED, 79, 80, 78, 79),
        ('SELL', MarginMode.ISOLATED, 121, 122, 120, 121),
    ],
)
def test_gap_beyond_liquidation_exits_before_other_protections(
    side: str,
    margin_mode: MarginMode,
    open_price: float,
    high: float,
    low: float,
    expected_price: float,
) -> None:
    first = _snapshot('2026-01-01 00:05')
    entry = _snapshot('2026-01-01 00:10')
    gap = _snapshot('2026-01-01 00:15', open_price=open_price, high=high, low=low, close=open_price)
    result = _run(
        _series(first, entry, gap),
        lambda snapshot, mode: _signal(snapshot, side) if snapshot is first else None,
        margin_mode=margin_mode,
    )
    trade = result.trades[0]
    assert trade.exit_reason == 'LIQUIDATION'
    assert trade.exit_price == expected_price
    assert trade.exit_time == gap.opened_at


@pytest.mark.parametrize(
    ('side', 'open_price', 'expected_price'),
    [('BUY', 90, 89.1), ('SELL', 110, 111.1)],
)
def test_gap_beyond_stop_uses_open_with_adverse_exit_slippage(
    side: str,
    open_price: float,
    expected_price: float,
) -> None:
    first = _snapshot('2026-01-01 00:05')
    entry = _snapshot('2026-01-01 00:10')
    gap = _snapshot(
        '2026-01-01 00:15',
        open_price=open_price,
        high=open_price + 1,
        low=open_price - 1,
        close=open_price,
    )
    result = _run(
        _series(first, entry, gap),
        lambda snapshot, mode: _signal(snapshot, side) if snapshot is first else None,
        slippage_rate=0.01,
    )
    trade = result.trades[0]
    assert trade.exit_reason == 'STOP'
    assert trade.exit_price == pytest.approx(expected_price)
    assert trade.exit_time == gap.opened_at


def test_gap_beyond_target_uses_open_time_and_fixed_target_price() -> None:
    first = _snapshot('2026-01-01 00:05')
    entry = _snapshot('2026-01-01 00:10')
    gap = _snapshot(
        '2026-01-01 00:15',
        open_price=120,
        high=121,
        low=119,
        close=120,
    )
    result = _run(
        _series(first, entry, gap),
        lambda snapshot, mode: _signal(snapshot) if snapshot is first else None,
    )
    trade = result.trades[0]
    assert trade.exit_reason == 'TARGET'
    assert trade.exit_price == 112
    assert trade.exit_time == gap.opened_at


def test_same_bar_stop_and_target_conflict_uses_stop() -> None:
    first = _snapshot('2026-01-01 00:05')
    conflict = _snapshot('2026-01-01 00:10', high=113, low=93)
    result = _run(
        _series(first, conflict),
        lambda snapshot, mode: _signal(snapshot) if snapshot is first else None,
    )
    assert result.trades[0].exit_reason == 'STOP'
    assert result.trades[0].exit_price == 94
    assert result.trades[0].exit_time == conflict.closed_at


def test_intrabar_move_hits_stop_before_more_distant_liquidation() -> None:
    first = _snapshot('2026-01-01 00:05')
    entry = _snapshot('2026-01-01 00:10')
    crash = _snapshot('2026-01-01 00:15', open_price=100, high=101, low=70, close=90)
    result = _run(
        _series(first, entry, crash),
        lambda snapshot, mode: _signal(snapshot) if snapshot is first else None,
    )
    assert result.trades[0].exit_reason == 'STOP'
    assert result.trades[0].exit_price == 94


@pytest.mark.parametrize(('side', 'expected_funding'), [('BUY', -0.05), ('SELL', 0.05)])
def test_intrabar_exit_excludes_funding_boundary_at_exit_time(
    side: str,
    expected_funding: float,
) -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry = _snapshot('2026-01-01 08:00', opened_at='2026-01-01 07:55')
    exit_bar = _snapshot(
        '2026-01-01 16:00',
        opened_at='2026-01-01 15:55',
        high=113 if side == 'BUY' else 101,
        low=99 if side == 'BUY' else 87,
    )
    result = _run(
        _series(first, entry, exit_bar),
        lambda snapshot, mode: _signal(snapshot, side) if snapshot is first else None,
        taker_fee=0.001,
        funding_rate=0.001,
    )
    trade = result.trades[0]
    assert trade.entry_commission == pytest.approx(0.05)
    assert trade.exit_reason == 'TARGET'
    assert trade.exit_time == exit_bar.closed_at
    assert trade.funding == pytest.approx(expected_funding)


def test_entry_exit_commissions_pnl_and_equity_are_accounted_once() -> None:
    first = _snapshot('2026-01-01 00:05')
    final = _snapshot('2026-01-01 00:10')
    result = _run(
        _series(first, final),
        lambda snapshot, mode: _signal(snapshot) if snapshot is first else None,
        taker_fee=0.001,
    )
    trade = result.trades[0]
    assert trade.entry_commission == pytest.approx(0.05)
    assert trade.exit_commission == pytest.approx(0.05)
    assert trade.pnl == pytest.approx(-0.10)
    assert trade.pnl_percent == pytest.approx(-1)
    assert result.equity_curve.iloc[-1] == pytest.approx(99.90)


def test_open_position_receives_funding_at_boundary_equal_to_bar_close() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry = _snapshot('2026-01-01 08:00', opened_at='2026-01-01 07:55')
    final = _snapshot('2026-01-01 16:00', opened_at='2026-01-01 15:55')
    result = _run(
        _series(first, entry, final),
        lambda snapshot, mode: _signal(snapshot) if snapshot is first else None,
        funding_rate=0.001,
    )
    trade = result.trades[0]
    assert trade.exit_reason == 'FINALIZE'
    assert trade.exit_time == final.closed_at
    assert trade.funding == pytest.approx(-0.10)
    assert trade.pnl == pytest.approx(-0.10)
    assert result.equity_curve.iloc[-1] == pytest.approx(99.90)


def test_gap_exit_excludes_funding_boundary_equal_to_open_time() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry = _snapshot('2026-01-01 08:00', opened_at='2026-01-01 07:55')
    gap = _snapshot(
        '2026-01-01 16:05',
        opened_at='2026-01-01 16:00',
        open_price=90,
        high=91,
        low=89,
        close=90,
    )
    result = _run(
        _series(first, entry, gap),
        lambda snapshot, mode: _signal(snapshot) if snapshot is first else None,
        funding_rate=0.001,
    )
    trade = result.trades[0]
    assert trade.exit_reason == 'STOP'
    assert trade.exit_time == gap.opened_at
    assert trade.funding == pytest.approx(-0.05)


def test_entry_commission_reduces_initial_cross_liquidation_collateral() -> None:
    first = _snapshot('2026-01-01 00:05')
    entry = _snapshot('2026-01-01 00:10')
    result = _run(
        _series(first, entry),
        lambda snapshot, mode: _signal(snapshot) if snapshot is first else None,
        margin_mode=MarginMode.CROSS,
        leverage=10,
        taker_fee=0.1,
    )
    assert result.trades[0].liquidation_price == pytest.approx(10 / 0.995)


def test_initial_cash_must_cover_opening_amount_and_entry_fee() -> None:
    with pytest.raises(ValueError, match='opening_amount and entry fee'):
        _run(
            _series(_snapshot('2026-01-01 00:05')),
            lambda snapshot, mode: None,
            opening_amount=100,
            taker_fee=0.001,
        )


def test_insufficient_cash_for_later_pending_fill_stops_without_new_trade() -> None:
    first = _snapshot('2026-01-01 00:05')
    first_entry_and_stop = _snapshot(
        '2026-01-01 00:10',
        high=101,
        low=70,
        close=80,
    )
    next_fill = _snapshot('2026-01-01 00:15')

    def dispatcher(snapshot: MarketSnapshot, mode: SignalMode) -> Signal:
        return replace(
            _signal(snapshot),
            stop_distance=20,
            target_distance=40,
        )

    result = _run(
        _series(first, first_entry_and_stop, next_fill),
        dispatcher,
        opening_amount=90,
        leverage=1,
        taker_fee=0.01,
    )
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == 'STOP'
    assert result.equity_curve.index[-1] == first_entry_and_stop.closed_at


def test_long_negative_funding_moves_dynamic_cross_liquidation_up() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry = _snapshot('2026-01-01 08:00', opened_at='2026-01-01 07:55')
    gap = _snapshot(
        '2026-01-01 08:05',
        opened_at='2026-01-01 08:00',
        open_price=15,
        high=16,
        low=14,
        close=15,
    )
    wide_signal = replace(
        _signal(first),
        stop_distance=200,
        target_distance=200,
    )
    result = _run(
        _series(first, entry, gap),
        lambda snapshot, mode: wide_signal if snapshot is first else None,
        margin_mode=MarginMode.CROSS,
        leverage=10,
        taker_fee=0.1,
        funding_rate=0.1,
    )
    assert result.trades[0].funding == -10
    assert result.trades[0].exit_reason == 'LIQUIDATION'
    assert result.trades[0].exit_time == gap.opened_at


def test_cross_liquidation_uses_funding_before_intrabar_exit() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry_and_crash = _snapshot(
        '2026-01-01 08:05',
        opened_at='2026-01-01 07:55',
        open_price=100,
        high=101,
        low=15,
        close=100,
    )
    wide_signal = replace(
        _signal(first),
        stop_distance=200,
        target_distance=200,
    )
    result = _run(
        _series(first, entry_and_crash),
        lambda snapshot, mode: wide_signal if snapshot is first else None,
        margin_mode=MarginMode.CROSS,
        leverage=10,
        taker_fee=0.1,
        funding_rate=0.1,
    )
    trade = result.trades[0]
    assert trade.funding == -10
    assert trade.exit_reason == 'LIQUIDATION'
    assert trade.exit_time == entry_and_crash.closed_at
    assert trade.liquidation_price == pytest.approx(trade.exit_price)


def test_close_boundary_funding_triggers_dynamic_cross_liquidation() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    closing_boundary = _snapshot(
        '2026-01-01 08:00',
        opened_at='2026-01-01 07:55',
        open_price=100,
        high=100,
        low=10.13,
        close=10.13,
    )
    wide_signal = replace(
        _signal(first),
        stop_distance=200,
        target_distance=200,
    )
    result = _run(
        _series(first, closing_boundary),
        lambda snapshot, mode: wide_signal if snapshot is first else None,
        margin_mode=MarginMode.CROSS,
        leverage=10,
        slippage_rate=0.01,
        funding_rate=0.1,
    )
    trade = result.trades[0]
    cash_after_funding = 90
    expected_threshold = (
        trade.notional_amount - cash_after_funding
    ) / (trade.quantity * (1 - 0.005))
    assert trade.exit_reason == 'LIQUIDATION'
    assert trade.exit_time == closing_boundary.closed_at
    assert trade.exit_price == pytest.approx(closing_boundary.close * 0.99)
    assert trade.liquidation_price == pytest.approx(expected_threshold)
    assert result.equity_curve.iloc[-1] == pytest.approx(100 + trade.pnl)


def test_negative_cross_cash_with_sufficient_long_profit_stays_open() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry = _snapshot(
        '2026-01-01 08:00',
        opened_at='2026-01-01 07:55',
        high=100,
        low=100,
    )
    profitable_gap = _snapshot(
        '2026-01-01 16:10',
        opened_at='2026-01-01 16:05',
        open_price=150,
        high=151,
        low=149,
        close=150,
    )
    wide_signal = replace(
        _signal(first),
        stop_distance=200,
        target_distance=200,
    )
    result = _run(
        _series(first, entry, profitable_gap),
        lambda snapshot, mode: wide_signal if snapshot is first else None,
        margin_mode=MarginMode.CROSS,
        leverage=10,
        funding_rate=0.51,
    )
    trade = result.trades[0]
    assert trade.exit_reason == 'FINALIZE'
    assert trade.exit_time == profitable_gap.closed_at
    assert trade.funding == -102
    assert result.equity_curve.iloc[-1] == pytest.approx(100 + trade.pnl)
    assert result.equity_curve.iloc[-1] > 0


def test_negative_cross_cash_with_sufficient_short_profit_is_below_threshold() -> None:
    first = _snapshot('2026-01-01 00:05')
    safe = _snapshot(
        '2026-01-01 00:10',
        open_price=50,
        high=60,
        low=40,
        close=50,
    )
    wide_signal = replace(
        _signal(first, 'SELL'),
        stop_distance=200,
        target_distance=200,
    )
    plan = build_trade_plan(
        wide_signal,
        fill_price=100,
        account_balance=100,
        opening_amount=10,
        leverage=10,
        margin_mode=MarginMode.CROSS,
    )
    threshold = _current_liquidation_price(plan, -10, 0.005)
    assert safe.open < threshold
    assert _exit_for_snapshot(
        plan,
        safe,
        0,
        threshold,
        phase='GAP',
    ) is None
    assert _exit_for_snapshot(
        plan,
        safe,
        0,
        threshold,
        phase='INTRABAR',
    ) is None


def test_negative_cross_cash_crossing_threshold_liquidates_at_gap_open() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry = _snapshot(
        '2026-01-01 08:00',
        opened_at='2026-01-01 07:55',
        high=100,
        low=100,
    )
    gap = _snapshot(
        '2026-01-01 16:10',
        opened_at='2026-01-01 16:05',
        open_price=100,
        high=101,
        low=99,
        close=100,
    )
    wide_signal = replace(
        _signal(first),
        stop_distance=200,
        target_distance=200,
    )
    result = _run(
        _series(first, entry, gap),
        lambda snapshot, mode: wide_signal if snapshot is first else None,
        margin_mode=MarginMode.CROSS,
        leverage=10,
        taker_fee=0.001,
        slippage_rate=0.01,
        funding_rate=0.5,
    )
    trade = result.trades[0]
    assert trade.exit_reason == 'LIQUIDATION'
    assert trade.exit_time == gap.opened_at
    assert trade.exit_price == 99
    assert trade.funding == -100
    assert trade.exit_commission == pytest.approx(trade.quantity * 99 * 0.001)
    cash_before_exit = 100 - trade.entry_commission + trade.funding
    expected_threshold = (
        trade.notional_amount - cash_before_exit
    ) / (trade.quantity * (1 - 0.005))
    assert trade.liquidation_price == pytest.approx(expected_threshold)
    assert result.equity_curve.iloc[-1] == pytest.approx(100 + trade.pnl)


def test_equity_curve_includes_fallback_liquidation_exit_costs() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry = _snapshot('2026-01-01 08:00', opened_at='2026-01-01 07:55')
    insolvent = _snapshot('2026-01-01 16:00', opened_at='2026-01-01 15:55')
    wide_signal = replace(
        _signal(first),
        stop_distance=200,
        target_distance=200,
    )
    result = _run(
        _series(first, entry, insolvent),
        lambda snapshot, mode: wide_signal if snapshot is first else None,
        leverage=10,
        taker_fee=0.001,
        slippage_rate=0.01,
        funding_rate=0.99,
    )
    trade = result.trades[0]
    assert trade.exit_reason == 'LIQUIDATION'
    assert trade.liquidation_price == pytest.approx(
        liquidation_price(
            'BUY',
            trade.fill_price,
            trade.leverage,
            trade.opening_amount,
            100 - trade.entry_commission,
            MarginMode.ISOLATED,
            0.005,
        )
    )
    assert result.equity_curve.iloc[-1] == pytest.approx(100 + trade.pnl)


def test_short_positive_funding_moves_dynamic_cross_liquidation_away() -> None:
    first = _snapshot('2026-01-01 07:55', opened_at='2026-01-01 07:50')
    entry = _snapshot('2026-01-01 08:00', opened_at='2026-01-01 07:55')
    gap = _snapshot(
        '2026-01-01 08:05',
        opened_at='2026-01-01 08:00',
        open_price=195,
        high=196,
        low=194,
        close=195,
    )
    wide_signal = replace(
        _signal(first, 'SELL'),
        stop_distance=200,
        target_distance=200,
    )
    result = _run(
        _series(first, entry, gap),
        lambda snapshot, mode: wide_signal if snapshot is first else None,
        margin_mode=MarginMode.CROSS,
        leverage=10,
        taker_fee=0.1,
        funding_rate=0.1,
    )
    assert result.trades[0].funding == 10
    assert result.trades[0].exit_reason == 'FINALIZE'


def test_pending_and_position_block_duplicate_dispatch_and_positions() -> None:
    snapshots = _series(
        _snapshot('2026-01-01 00:05'),
        _snapshot('2026-01-01 00:10'),
        _snapshot('2026-01-01 00:15'),
    )
    calls: list[pd.Timestamp] = []

    def dispatcher(snapshot: MarketSnapshot, mode: SignalMode) -> Signal:
        calls.append(snapshot.closed_at)
        return _signal(snapshot)

    result = _run(snapshots, dispatcher)

    assert calls == [snapshots.iloc[0].closed_at]
    assert len(result.trades) == 1
    assert result.maximum_concurrent_positions == 1


def test_pullback_candidate_uses_its_state_machine_and_emits_one_trade() -> None:
    event = _snapshot(
        '2026-01-01 00:05',
        open_price=97,
        high=98,
        low=94,
        close=96,
    )
    confirmation = _snapshot(
        '2026-01-01 00:10',
        open_price=95,
        high=98,
        low=95,
        close=97,
    )
    final = _snapshot('2026-01-01 00:15')

    result = SignalSimulator().run(
        _series(event, confirmation, final),
        mode=SignalMode.PULLBACK_CONFIRMATION,
        cash=100,
        opening_amount=10,
        leverage=5,
        margin_mode=MarginMode.ISOLATED,
        taker_fee=0,
        slippage_rate=0,
        funding_rate=0,
        maintenance_margin_rate=0.005,
    )

    assert len(result.trades) == 1
    assert result.trades[0].strategy == 'PULLBACK_CONFIRMATION'
    assert result.trades[0].signal_time == confirmation.closed_at


def test_empty_input_returns_empty_result() -> None:
    result = _run(
        pd.Series(dtype=object, index=pd.DatetimeIndex([], tz='UTC')),
        lambda snapshot, mode: None,
    )
    assert result.trades == ()
    assert result.equity_curve.empty
    assert result.maximum_concurrent_positions == 0


@pytest.mark.parametrize(
    ('overrides', 'message'),
    [
        ({'cash': 0}, 'cash'),
        ({'opening_amount': 0}, 'opening_amount'),
        ({'opening_amount': 101}, 'opening_amount'),
        ({'leverage': 0}, 'leverage'),
        ({'taker_fee': -0.1}, 'taker_fee'),
        ({'taker_fee': 1}, 'taker_fee'),
        ({'slippage_rate': 1}, 'slippage_rate'),
        ({'funding_rate': -0.1}, 'funding_rate'),
        ({'funding_rate': 1}, 'funding_rate'),
        ({'maintenance_margin_rate': 1}, 'maintenance_margin_rate'),
    ],
)
def test_invalid_run_parameters_raise(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _run(_series(_snapshot('2026-01-01 00:05')), lambda snapshot, mode: None, **overrides)


def test_invalid_snapshot_prices_and_indexes_raise() -> None:
    valid = _snapshot('2026-01-01 00:05')
    with pytest.raises(ValueError, match='prices'):
        _run(_series(replace(valid, high=99)), lambda snapshot, mode: None)

    duplicate = pd.Series(
        [valid, valid],
        index=pd.DatetimeIndex([valid.closed_at, valid.closed_at]),
        dtype=object,
    )
    with pytest.raises(ValueError, match='unique'):
        _run(duplicate, lambda snapshot, mode: None)

    reversed_series = _series(valid, _snapshot('2026-01-01 00:04'))
    with pytest.raises(ValueError, match='increasing'):
        _run(reversed_series, lambda snapshot, mode: None)

    with pytest.raises(ValueError, match='opened_at'):
        _run(
            _series(replace(valid, opened_at=valid.closed_at)),
            lambda snapshot, mode: None,
        )
