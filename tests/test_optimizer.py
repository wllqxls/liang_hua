from dataclasses import asdict

from src.backtest.optimizer import (
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
        SearchCandidate('A', '15m', '5m', 192, 30, 5, 1, 1),
        SearchCandidate('B', '1h', '15m', 96, 20, 10, 1.5, 0.75),
    ]

    first = build_stage_two_candidates(ranked, seed_key='BTC/USDT|fees', per_candidate=6)
    second = build_stage_two_candidates(ranked, seed_key='BTC/USDT|fees', per_candidate=6)

    assert first == second
    assert len(first) <= 12
    assert all(item in first for item in set(first))
