from dataclasses import asdict

from src.backtest.optimizer import (
    LEVERAGE_OPTIONS,
    SearchCandidate,
    available_entry_timeframes,
    build_stage_one_candidates,
    build_stage_two_candidates,
)
from src.strategies.signal_models import MarginMode, SignalMode


def test_available_entry_timeframes_require_entry_1h_and_4h_files(tmp_path) -> None:
    for timeframe in ['5m', '1h', '4h']:
        (tmp_path / f'BTC_USDT_{timeframe}.csv').touch()
    (tmp_path / 'ETH_USDT_15m.csv').touch()
    (tmp_path / 'ETH_USDT_1h.csv').touch()

    assert available_entry_timeframes(tmp_path, 'BTC/USDT') == ['5m']
    assert available_entry_timeframes(tmp_path, 'ETH/USDT') == []


def test_stage_one_is_deterministic_and_covers_modes_by_available_timeframe() -> None:
    kwargs = {
        'entry_timeframes': ['5m', '15m'],
        'modes': list(SignalMode),
        'margin_mode': MarginMode.CROSS,
        'current_leverage': 7,
        'seed_key': 'BTC/USDT|CROSS|fees',
    }

    first = build_stage_one_candidates(**kwargs)
    second = build_stage_one_candidates(**kwargs)

    assert first == second
    assert len(first) == 6
    assert {(item.mode, item.timeframe) for item in first} == {
        (mode, timeframe) for mode in SignalMode for timeframe in ['5m', '15m']
    }
    assert {item.leverage for item in first} == {7.0}
    assert {item.margin_mode for item in first} == {MarginMode.CROSS}


def test_candidate_shape_contains_only_approved_search_dimensions() -> None:
    candidate = SearchCandidate(
        mode=SignalMode.KEY_LEVEL,
        timeframe='5m',
        leverage=5,
        margin_mode=MarginMode.ISOLATED,
    )

    assert set(asdict(candidate)) == {'mode', 'timeframe', 'leverage', 'margin_mode'}


def test_stage_two_is_deterministic_and_only_explores_adjacent_leverage() -> None:
    ranked = [
        SearchCandidate(SignalMode.KEY_LEVEL, '5m', 5, MarginMode.ISOLATED),
        SearchCandidate(SignalMode.RSI_REVERSAL, '15m', 125, MarginMode.ISOLATED),
    ]

    first = build_stage_two_candidates(ranked, seed_key='BTC/USDT|ISOLATED|fees')
    second = build_stage_two_candidates(ranked, seed_key='BTC/USDT|ISOLATED|fees')

    assert first == second
    assert {item.leverage for item in first if item.mode is SignalMode.KEY_LEVEL} == {3.0, 10.0}
    assert {item.leverage for item in first if item.mode is SignalMode.RSI_REVERSAL} == {100.0, 150.0}
    assert {item.margin_mode for item in first} == {MarginMode.ISOLATED}
    assert all(item.leverage in LEVERAGE_OPTIONS for item in first)


def test_stage_two_does_not_repeat_exact_unlisted_base() -> None:
    base = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)

    candidates = build_stage_two_candidates([base], seed_key='seven-x')

    assert {item.leverage for item in candidates} == {5.0, 10.0}
    assert len(candidates) == 2
