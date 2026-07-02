from dataclasses import asdict

from src.backtest.optimizer import (
    LEVERAGE_OPTIONS,
    SearchCandidate,
    available_timeframe_pairs,
    build_stage_one_candidates,
    build_stage_two_candidates,
)


def test_available_timeframe_pairs_only_use_existing_ordered_data(tmp_path) -> None:
    for timeframe in ['5m', '15m', '1h']:
        (tmp_path / f'BTC_USDT_{timeframe}.csv').touch()

    assert available_timeframe_pairs(tmp_path, 'BTC/USDT') == [
        ('15m', '5m'),
        ('1h', '5m'),
        ('1h', '15m'),
    ]


def test_stage_one_sampling_is_deterministic_and_stratified() -> None:
    kwargs = {
        'timeframe_pairs': [('15m', '5m'), ('1h', '15m')],
        'strategies': ['A', 'B'],
        'current_leverage': 5,
        'take_profit_amount': 1,
        'stop_loss_amount': 1,
        'position_amount': 10,
        'seed_key': 'BTC/USDT|fees',
        'budget': 24,
    }

    first = build_stage_one_candidates(**kwargs)
    second = build_stage_one_candidates(**kwargs)

    assert first == second
    assert len(first) == 24
    assert {(item.strategy, item.context_timeframe, item.timeframe) for item in first} == {
        ('A', '15m', '5m'),
        ('A', '1h', '15m'),
        ('B', '15m', '5m'),
        ('B', '1h', '15m'),
    }
    assert 'position_amount' not in asdict(first[0])
    assert 'backtest_days' not in asdict(first[0])


def test_stage_two_search_is_bounded_and_deterministic() -> None:
    ranked = [
        SearchCandidate(f'S{index}', '15m', '5m', 192, 30, 5, 1, 1)
        for index in range(12)
    ]

    first = build_stage_two_candidates(
        ranked,
        seed_key='BTC/USDT|fees',
        position_amount=10,
        per_candidate=6,
    )
    second = build_stage_two_candidates(
        ranked,
        seed_key='BTC/USDT|fees',
        position_amount=10,
        per_candidate=6,
    )

    assert first == second
    assert len(first) == 84
    for index in range(3):
        assert {item.leverage for item in first if item.strategy == f'S{index}'} == {
            float(value) for value in LEVERAGE_OPTIONS
        }
    for index in range(3, 12):
        candidates = [item for item in first if item.strategy == f'S{index}']
        assert len(candidates) == 6
        assert {item.leverage for item in candidates} <= {3.0, 5.0, 10.0}


def test_stage_two_preserves_exit_distances_across_leverage_changes() -> None:
    base = SearchCandidate('SRBreakout', '1h', '5m', 192, 30, 10, 1.5, 0.5)

    candidates = build_stage_two_candidates(
        [base],
        seed_key='ETH/USDT|fees',
        position_amount=2,
    )

    assert any(
        item.leverage == 3
        and item.context_lookback == 192
        and item.entry_lookback == 30
        and item.take_profit_amount == 0.45
        and item.stop_loss_amount == 0.15
        for item in candidates
    )
