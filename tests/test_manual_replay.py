from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from src.backtest.manual_replay import ManualReplay, _normalize_funding_rates
from src.strategies.manual_candidates import validate_manual_candidate_scope
from src.strategies.signal_models import (
    FilterLabel,
    ManualSignalMode,
    MarginMode,
    MarketSnapshot,
    Signal,
    SignalMode,
)


def _snapshot(index: int, *, close: float = 100.0, high: float = 101.0, low: float = 99.0) -> MarketSnapshot:
    opened = pd.Timestamp('2025-01-01', tz='UTC') + pd.Timedelta(minutes=5 * index)
    return MarketSnapshot(
        opened_at=opened, closed_at=opened + pd.Timedelta(minutes=5), open=100.0,
        high=high, low=low, close=close, atr=1.0, rsi=50.0,
        bollinger_upper=110.0, bollinger_lower=90.0, previous_high_20=105.0,
        previous_low_20=95.0, environment_side='BUY', filter_label=FilterLabel.NEUTRAL,
        context_1h_closed_at=opened, context_4h_closed_at=opened,
    )


def _signal(snapshot: MarketSnapshot, *, reason: str = 'fixture') -> Signal:
    return Signal(
        mode=SignalMode.KEY_LEVEL, strategy='KEY_LEVEL', side='BUY', signal_time=snapshot.closed_at,
        signal_close=snapshot.close, atr_snapshot=1.0, stop_atr_multiple=1.0,
        target_atr_multiple=1.0, stop_distance=1.0, target_distance=1.0,
        estimated_stop_price=99.0, estimated_target_price=101.0,
        environment_side='BUY', filter_label=FilterLabel.NEUTRAL, reason=reason, score=1,
    )


def _replay() -> ManualReplay:
    snapshots = pd.Series([_snapshot(0), _snapshot(1, high=102.0), _snapshot(2)], index=pd.date_range('2025-01-01 00:05', periods=3, freq='5min', tz='UTC'))
    frame = pd.DataFrame({'Open': [100.0], 'High': [101.0], 'Low': [99.0], 'Close': [100.0]}, index=pd.date_range('2025-01-01', periods=1, freq='5min', tz='UTC'))
    return ManualReplay('id', 'BTC/USDT', '5m', 2025, SignalMode.KEY_LEVEL, snapshots, {'5m': frame, '15m': frame, '1h': frame}, 100.0, 10.0, 1.0, 0.0, 0.0)


def test_visible_payload_contains_only_cursor_prefix() -> None:
    replay = _replay()
    payload = replay.visible_payload()
    assert len(payload['candles']) == 1
    assert len(payload['charts']['5m']) == 1


def test_manual_buy_uses_next_open_and_stop_first_conservative_exit() -> None:
    replay = _replay()
    replay.state = 'AWAITING_DECISION'
    replay.pending_signal = _signal(replay.snapshots.iloc[0])

    replay.decide('BUY')

    assert len(replay.trades) == 1
    assert replay.trades[0].exit_reason == 'STOP'
    assert replay.trades[0].fill_time == replay.snapshots.iloc[1].opened_at
    assert replay.state == 'AWAITING_CONTINUE'


def test_manual_trade_applies_configured_taker_fee_and_slippage_on_both_sides() -> None:
    replay = _replay()
    replay.taker_fee = 0.001
    replay.slippage_rate = 0.002
    replay.state = 'AWAITING_DECISION'
    replay.pending_signal = _signal(replay.snapshots.iloc[0])

    replay.decide('BUY')

    trade = replay.trades[0]
    expected_fill = 100.0 * 1.002
    expected_exit = (expected_fill - 1.0) * (1 - 0.002)
    quantity = 10.0 / expected_fill
    expected_pnl = quantity * (expected_exit - expected_fill) - 10.0 * 0.001 - quantity * expected_exit * 0.001
    assert trade.fill_price == pytest.approx(expected_fill)
    assert trade.exit_price == pytest.approx(expected_exit)
    assert trade.pnl == pytest.approx(expected_pnl)
    assert trade.equity == pytest.approx(100.0 + expected_pnl)


def test_skip_does_not_create_trade() -> None:
    replay = _replay()
    replay.state = 'AWAITING_DECISION'
    replay.pending_signal = _signal(replay.snapshots.iloc[0])

    replay.decide('SKIP')

    assert not replay.trades
    assert replay.decisions[0]['decision'] == 'SKIP'
    marker = replay.visible_payload()['signal_markers'][0]
    assert marker['time'] == int(_signal(replay.snapshots.iloc[0]).signal_time.timestamp()) - 300
    assert marker['summary'] == '候选做多'


def test_open_position_advances_one_candle_at_a_time_then_waits_to_continue() -> None:
    snapshots = pd.Series(
        [
            _snapshot(0),
            _snapshot(1, high=100.5, low=99.5),
            _snapshot(2, high=101.5, low=99.8),
            _snapshot(3),
        ],
        index=pd.date_range('2025-01-01 00:05', periods=4, freq='5min', tz='UTC'),
    )
    replay = _replay()
    replay.snapshots = snapshots
    replay.state = 'AWAITING_DECISION'
    replay.pending_signal = _signal(snapshots.iloc[0])

    replay.decide('BUY')

    assert replay.state == 'POSITION_OPEN'
    assert replay.cursor == 1
    assert not replay.trades
    open_overlay = replay.visible_payload()['position_overlay']
    assert open_overlay['status'] == 'OPEN'
    assert open_overlay['entry_time'] == int(snapshots.iloc[1].opened_at.timestamp())
    assert open_overlay['liquidation_price'] >= 0
    assert open_overlay['margin_mode_label'] == '逐仓'
    assert len(replay.visible_payload()['candles']) == 2

    replay.step_position()

    assert replay.cursor == 2
    assert replay.state == 'AWAITING_CONTINUE'
    assert replay.trades[0].exit_reason == 'TARGET'
    closed_overlay = replay.visible_payload()['position_overlay']
    assert closed_overlay['status'] == 'CLOSED'
    assert closed_overlay['end_time'] == int(snapshots.iloc[2].opened_at.timestamp())
    replay.advance(max_bars=40)
    assert replay.cursor == 2
    assert replay.state == 'AWAITING_CONTINUE'

    replay.continue_after_exit()

    assert replay.state == 'RUNNING'
    assert replay.visible_payload()['position_overlay'] is None


def test_position_step_and_continue_reject_wrong_states() -> None:
    replay = _replay()

    with pytest.raises(ValueError, match='open position'):
        replay.step_position()
    with pytest.raises(ValueError, match='waiting to continue'):
        replay.continue_after_exit()


def test_pending_signal_uses_chinese_reason_and_event_candle_open_time() -> None:
    replay = _replay()
    replay.state = 'AWAITING_DECISION'
    replay.pending_signal = _signal(
        replay.snapshots.iloc[0],
        reason='False break below the previous 20-candle low',
    )

    signal = replay.visible_payload()['signal']

    assert signal['reason'] == '跌破前 20 根 K 线低点后重新收回，可能是假跌破'
    assert signal['time'] == int(replay.snapshots.iloc[0].opened_at.timestamp())


def test_order_flow_candidate_pauses_on_matching_open_time_without_future_labels() -> None:
    replay = _replay()
    replay.mode = ManualSignalMode.ORDER_FLOW_FADING_15M
    replay.timeframe = '15m'
    replay.candidate_features = pd.DataFrame(
        {
            'taker_buy_ratio': [0.568],
            'oi_change_45m': [0.0023],
            'funding_rate': [0.0001],
        },
        index=pd.DatetimeIndex([replay.snapshots.iloc[0].opened_at]),
    )

    replay.advance(max_bars=1)

    assert replay.state == 'AWAITING_DECISION'
    assert replay.pending_signal is not None
    assert replay.pending_signal.side == 'SELL'
    assert '主动买入占比 56.8%' in replay.pending_signal.reason
    assert '45 分钟 OI 增长 0.23%' in replay.pending_signal.reason


def test_manual_experimental_scopes_are_frozen() -> None:
    with pytest.raises(ValueError, match='15m'):
        validate_manual_candidate_scope(
            mode=ManualSignalMode.ORDER_FLOW_FADING_15M,
            symbol='BTC/USDT',
            timeframe='5m',
            year=2025,
        )
    with pytest.raises(ValueError, match='ETH/USDT'):
        validate_manual_candidate_scope(
            mode=ManualSignalMode.ETH_RSI_WHITELIST_5M,
            symbol='BTC/USDT',
            timeframe='5m',
            year=2025,
        )


def test_high_leverage_isolated_position_liquidates_before_invalid_stop() -> None:
    replay = _replay()
    replay.leverage = 100.0
    replay.margin_mode = MarginMode.ISOLATED
    replay.maintenance_margin_rate = 0.005
    replay.liquidation_fee_rate = 0.005
    replay.state = 'AWAITING_DECISION'
    replay.pending_signal = _signal(replay.snapshots.iloc[0])

    replay.decide('BUY')

    trade = replay.trades[0]
    assert trade.exit_reason == 'LIQUIDATION'
    assert trade.liquidation_price > trade.stop_price
    assert trade.exit_price == pytest.approx(trade.liquidation_price)
    assert trade.liquidation_fee == pytest.approx(
        replay.opening_amount * replay.leverage / trade.fill_price
        * trade.exit_price * replay.liquidation_fee_rate
    )
    payload = replay.visible_payload()
    assert payload['trades'][0]['exit_reason_label'] == '强平'
    assert payload['position_overlay']['exit_reason_label'] == '强平'


def test_cross_margin_uses_account_cash_and_reaches_stop_before_liquidation() -> None:
    replay = _replay()
    replay.leverage = 100.0
    replay.margin_mode = MarginMode.CROSS
    replay.maintenance_margin_rate = 0.005
    replay.state = 'AWAITING_DECISION'
    replay.pending_signal = _signal(replay.snapshots.iloc[0])

    replay.decide('BUY')

    trade = replay.trades[0]
    assert trade.exit_reason == 'STOP'
    assert trade.liquidation_price < trade.stop_price
    assert trade.margin_mode is MarginMode.CROSS
    assert trade.liquidation_fee == 0


@pytest.mark.parametrize(
    ('decision', 'exit_high', 'exit_low', 'expected_funding'),
    [('BUY', 101.5, 99.8, -0.01), ('SELL', 100.2, 98.5, 0.01)],
)
def test_manual_trade_applies_local_funding_once_at_real_settlement(
    decision: str,
    exit_high: float,
    exit_low: float,
    expected_funding: float,
) -> None:
    opened = pd.Timestamp('2025-01-01 07:50', tz='UTC')
    snapshots = pd.Series(
        [
            _snapshot(0),
            _snapshot(1, high=100.5, low=99.5),
            _snapshot(2, high=exit_high, low=exit_low),
        ],
        index=pd.date_range('2025-01-01 07:55', periods=3, freq='5min', tz='UTC'),
    )
    snapshots = pd.Series(
        [
            replace(
                snapshot,
                opened_at=opened + pd.Timedelta(minutes=5 * index),
                closed_at=opened + pd.Timedelta(minutes=5 * (index + 1)),
            )
            for index, snapshot in enumerate(snapshots)
        ],
        index=pd.date_range('2025-01-01 07:55', periods=3, freq='5min', tz='UTC'),
    )
    frame = pd.DataFrame(
        {'Open': [100.0, 100.0], 'High': [100.5, 101.5], 'Low': [99.5, 98.5], 'Close': [100.0, 100.0]},
        index=pd.date_range('2025-01-01 07:50', periods=2, freq='5min', tz='UTC'),
    )
    replay = ManualReplay(
        'id', 'BTC/USDT', '5m', 2025, SignalMode.KEY_LEVEL, snapshots,
        {'5m': frame, '15m': frame, '1h': frame}, 100.0, 10.0, 1.0, 0.0, 0.0,
    )
    replay.funding_rates = pd.Series(
        [0.001], index=pd.DatetimeIndex(['2025-01-01 08:00:00+00:00']),
    )
    replay.state = 'AWAITING_DECISION'
    replay.pending_signal = _signal(snapshots.iloc[0])

    replay.decide(decision)
    assert replay.state == 'POSITION_OPEN'
    assert replay.active_position is not None
    assert replay.active_position.funding == pytest.approx(expected_funding)

    replay.step_position()

    trade = replay.trades[0]
    assert trade.funding == pytest.approx(expected_funding)
    assert replay.visible_payload()['trades'][0]['funding'] == pytest.approx(expected_funding)
    assert replay.visible_payload()['funding_available'] is True


def test_funding_timestamp_millisecond_jitter_is_aligned_to_settlement_minute() -> None:
    rates = pd.Series(
        [0.0001],
        index=pd.DatetimeIndex(['2025-01-01 08:00:00.015000+00:00']),
    )

    normalized = _normalize_funding_rates(rates)

    assert normalized.index[0] == pd.Timestamp('2025-01-01 08:00:00+00:00')
