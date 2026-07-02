from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from src.strategies.market_context import build_market_snapshots
from src.strategies.signal_models import (
    FilterLabel,
    MarginMode,
    MarketSnapshot,
    SignalMode,
)


def _candles(index: pd.DatetimeIndex, closes: list[float]) -> pd.DataFrame:
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            'Open': close,
            'High': close + 1,
            'Low': close - 1,
            'Close': close,
            'Volume': 100.0,
        }
    )


def _frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    entry_index = pd.date_range('2026-01-01', periods=300, freq='5min', tz='UTC')
    hour_index = pd.date_range('2025-12-30', periods=72, freq='1h', tz='UTC')
    four_hour_index = pd.date_range('2025-12-24', periods=60, freq='4h', tz='UTC')
    return (
        _candles(entry_index, [100 + index for index in range(300)]),
        _candles(hour_index, [100 + index for index in range(72)]),
        _candles(four_hour_index, [100 + index for index in range(60)]),
    )


def test_signal_contracts_are_stable_strings_and_snapshots_are_immutable() -> None:
    assert str(SignalMode.KEY_LEVEL_RSI) == 'KEY_LEVEL_RSI'
    assert str(MarginMode.ISOLATED) == 'ISOLATED'
    assert FilterLabel.LONG.value == 'FILTER_LONG'

    snapshot = MarketSnapshot(
        closed_at=pd.Timestamp('2026-01-01 00:05', tz='UTC'),
        open=100,
        high=101,
        low=99,
        close=100,
        atr=2,
        rsi=50,
        bollinger_upper=110,
        bollinger_lower=90,
        previous_high_20=105,
        previous_low_20=95,
        environment_side='BUY',
        filter_label=FilterLabel.LONG,
        context_1h_closed_at=pd.Timestamp('2026-01-01', tz='UTC'),
        context_4h_closed_at=pd.Timestamp('2026-01-01', tz='UTC'),
    )

    with pytest.raises(FrozenInstanceError):
        snapshot.close = 101  # type: ignore[misc]
    assert not hasattr(snapshot, '__dict__')


def test_snapshot_never_reads_unclosed_hour_or_four_hour_bar() -> None:
    entry, hour, four_hour = _frames()
    hour.loc[pd.Timestamp('2026-01-01 01:00', tz='UTC'), 'Close'] = -1_000_000
    four_hour.loc[pd.Timestamp('2026-01-01 00:00', tz='UTC'), 'Close'] = -1_000_000

    snapshots = build_market_snapshots(entry, hour, four_hour, timeframe='5m')

    before_hour_close = snapshots.loc[pd.Timestamp('2026-01-01 01:55', tz='UTC')]
    at_hour_close = snapshots.loc[pd.Timestamp('2026-01-01 02:00', tz='UTC')]
    before_four_hour_close = snapshots.loc[pd.Timestamp('2026-01-01 03:55', tz='UTC')]
    at_four_hour_close = snapshots.loc[pd.Timestamp('2026-01-01 04:00', tz='UTC')]
    assert before_hour_close.context_1h_closed_at == pd.Timestamp(
        '2026-01-01 01:00', tz='UTC'
    )
    assert at_hour_close.context_1h_closed_at == pd.Timestamp(
        '2026-01-01 02:00', tz='UTC'
    )
    assert before_four_hour_close.context_4h_closed_at == pd.Timestamp(
        '2026-01-01 00:00', tz='UTC'
    )
    assert at_four_hour_close.context_4h_closed_at == pd.Timestamp(
        '2026-01-01 04:00', tz='UTC'
    )
    assert before_hour_close.environment_side == 'BUY'
    assert at_hour_close.environment_side == 'SELL'
    assert before_four_hour_close.filter_label is FilterLabel.LONG
    assert at_four_hour_close.filter_label is FilterLabel.SHORT


def test_entry_features_use_close_time_and_previous_key_levels() -> None:
    entry, hour, four_hour = _frames()

    snapshots = build_market_snapshots(entry, hour, four_hour, timeframe='5m')

    snapshot = snapshots.loc[pd.Timestamp('2026-01-01 01:45', tz='UTC')]
    assert snapshot.closed_at == pd.Timestamp('2026-01-01 01:45', tz='UTC')
    assert snapshot.close == 120
    assert snapshot.previous_high_20 == 120
    assert snapshot.previous_low_20 == 99


def test_snapshot_accepts_fifteen_minutes_and_sorts_indexes() -> None:
    entry, hour, four_hour = _frames()
    entry = entry.iloc[::3].iloc[::-1]
    hour = hour.iloc[::-1]
    four_hour = four_hour.iloc[::-1]

    snapshots = build_market_snapshots(entry, hour, four_hour, timeframe='15m')

    assert snapshots.index.is_monotonic_increasing
    assert snapshots.index[0] == entry.sort_index().index[20] + pd.Timedelta(minutes=15)


def test_snapshot_omits_entries_before_first_higher_timeframe_close() -> None:
    entry_index = pd.date_range('2026-01-01', periods=40, freq='5min', tz='UTC')
    hour_index = pd.date_range('2026-01-01 04:00', periods=20, freq='1h', tz='UTC')
    four_hour_index = pd.date_range(
        '2026-01-01 04:00', periods=30, freq='4h', tz='UTC'
    )

    snapshots = build_market_snapshots(
        _candles(entry_index, list(range(40))),
        _candles(hour_index, list(range(20))),
        _candles(four_hour_index, list(range(30))),
        timeframe='5m',
    )

    assert snapshots.empty


@pytest.mark.parametrize('empty_name', ['hour', 'four_hour'])
def test_snapshot_returns_empty_when_context_is_empty(empty_name: str) -> None:
    entry, hour, four_hour = _frames()
    frames = {'hour': hour, 'four_hour': four_hour}
    frames[empty_name] = frames[empty_name].iloc[:0]

    snapshots = build_market_snapshots(
        entry, frames['hour'], frames['four_hour'], timeframe='5m'
    )

    assert snapshots.empty


@pytest.mark.parametrize(
    ('hour_periods', 'four_hour_periods'),
    [(19, 40), (40, 29)],
)
def test_snapshot_omits_context_until_ema_warmup_is_complete(
    hour_periods: int,
    four_hour_periods: int,
) -> None:
    entry, _, _ = _frames()
    hour_index = pd.date_range(
        '2025-12-01', periods=hour_periods, freq='1h', tz='UTC'
    )
    four_hour_index = pd.date_range(
        '2025-12-01', periods=four_hour_periods, freq='4h', tz='UTC'
    )

    snapshots = build_market_snapshots(
        entry,
        _candles(hour_index, list(range(hour_periods))),
        _candles(four_hour_index, list(range(four_hour_periods))),
        timeframe='5m',
    )

    assert snapshots.empty


def test_snapshot_omits_entries_until_all_entry_indicators_are_ready() -> None:
    entry, hour, four_hour = _frames()

    snapshots = build_market_snapshots(entry.iloc[:20], hour, four_hour, timeframe='5m')

    assert snapshots.empty


def test_every_snapshot_has_finite_indicators_and_real_context_times() -> None:
    entry, hour, four_hour = _frames()

    snapshots = build_market_snapshots(entry, hour, four_hour, timeframe='5m')

    assert not snapshots.empty
    for snapshot in snapshots:
        assert snapshot.environment_side in {'BUY', 'SELL'}
        assert isinstance(snapshot.context_1h_closed_at, pd.Timestamp)
        assert isinstance(snapshot.context_4h_closed_at, pd.Timestamp)
        assert not pd.isna(snapshot.context_1h_closed_at)
        assert not pd.isna(snapshot.context_4h_closed_at)
        assert np.isfinite(
            [
                snapshot.atr,
                snapshot.rsi,
                snapshot.bollinger_upper,
                snapshot.bollinger_lower,
                snapshot.previous_high_20,
                snapshot.previous_low_20,
            ]
        ).all()


def test_snapshot_omits_derived_non_finite_indicators() -> None:
    entry, hour, four_hour = _frames()
    entry['High'] = 1e308
    entry['Low'] = -1e308

    with np.errstate(over='ignore', invalid='ignore'):
        snapshots = build_market_snapshots(entry, hour, four_hour, timeframe='5m')

    assert snapshots.empty


@pytest.mark.parametrize('timeframe', ['1m', '1h', '5min', ''])
def test_snapshot_rejects_unsupported_entry_timeframes(timeframe: str) -> None:
    entry, hour, four_hour = _frames()

    with pytest.raises(ValueError, match='5m or 15m'):
        build_market_snapshots(entry, hour, four_hour, timeframe=timeframe)


@pytest.mark.parametrize('frame_name', ['entry', 'hour', 'four_hour'])
def test_snapshot_requires_timezone_aware_datetime_indexes(frame_name: str) -> None:
    entry, hour, four_hour = _frames()
    frames = {'entry': entry, 'hour': hour, 'four_hour': four_hour}
    frames[frame_name] = frames[frame_name].tz_localize(None)

    with pytest.raises(ValueError, match='timezone-aware DatetimeIndex'):
        build_market_snapshots(
            frames['entry'], frames['hour'], frames['four_hour'], timeframe='5m'
        )


def test_snapshot_aligns_equivalent_timezones() -> None:
    entry, hour, four_hour = _frames()
    hour.index = hour.index.tz_convert('Asia/Shanghai')

    snapshots = build_market_snapshots(entry, hour, four_hour, timeframe='5m')

    assert snapshots.loc[pd.Timestamp('2026-01-01 01:45', tz='UTC')].context_1h_closed_at == pd.Timestamp(
        '2026-01-01 01:00', tz='UTC'
    )


@pytest.mark.parametrize('frame_name', ['entry', 'hour', 'four_hour'])
@pytest.mark.parametrize('column', ['Open', 'High', 'Low', 'Close'])
def test_snapshot_rejects_missing_price_columns(frame_name: str, column: str) -> None:
    entry, hour, four_hour = _frames()
    frames = {'entry': entry, 'hour': hour, 'four_hour': four_hour}
    frames[frame_name] = frames[frame_name].drop(columns=column)

    with pytest.raises(ValueError, match='missing required columns'):
        build_market_snapshots(
            frames['entry'], frames['hour'], frames['four_hour'], timeframe='5m'
        )


@pytest.mark.parametrize('frame_name', ['entry', 'hour', 'four_hour'])
@pytest.mark.parametrize('invalid', [np.nan, np.inf, -np.inf, 'bad'])
def test_snapshot_rejects_non_finite_prices(frame_name: str, invalid: object) -> None:
    entry, hour, four_hour = _frames()
    frames = {'entry': entry, 'hour': hour, 'four_hour': four_hour}
    if isinstance(invalid, str):
        frames[frame_name]['Close'] = frames[frame_name]['Close'].astype(object)
    frames[frame_name].iloc[0, frames[frame_name].columns.get_loc('Close')] = invalid

    with pytest.raises(ValueError, match='finite numbers'):
        build_market_snapshots(
            frames['entry'], frames['hour'], frames['four_hour'], timeframe='5m'
        )
