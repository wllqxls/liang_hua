from __future__ import annotations

import pandas as pd
import pytest

from src.backtest.manual_replay import ManualReplay
from src.strategies.signal_models import FilterLabel, MarketSnapshot, Signal, SignalMode


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
