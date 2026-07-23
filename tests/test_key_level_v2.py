import numpy as np
import pandas as pd
import pytest

import src.strategies.key_level_v2 as key_level_v2
from src.strategies.indicators import atr_wilder
from src.strategies.key_level_v2 import (
    MIN_REWARD_RISK,
    STOP_BUFFER_ATR_MULTIPLE,
    TARGET_BUFFER_ATR_MULTIPLE,
    build_key_level_candidates,
    structural_reward_risk,
)
from src.strategies.manual_candidates import evaluate_manual_candidate
from src.strategies.signal_models import FilterLabel, ManualSignalMode, MarketSnapshot


def _price_frame(rows: int = 90, *, include_target: bool = True) -> pd.DataFrame:
    index = pd.date_range('2025-01-01', periods=rows, freq='5min', tz='UTC')
    base = np.linspace(0.0, 0.15, rows)
    frame = pd.DataFrame(
        {
            'Open': 102.0 + base,
            'High': 102.6 + base,
            'Low': 101.4 + base,
            'Close': 102.1 + base,
            'Volume': 1000.0,
        },
        index=index,
    )
    for pivot_index in (20, 35, 50, 65):
        frame.iloc[pivot_index, frame.columns.get_loc('Low')] = 98.8
        frame.iloc[pivot_index, frame.columns.get_loc('Open')] = 99.2
        frame.iloc[pivot_index, frame.columns.get_loc('Close')] = 99.6
    if include_target:
        for pivot_index in (25, 40, 55, 70):
            frame.iloc[pivot_index, frame.columns.get_loc('High')] = 106.0
            frame.iloc[pivot_index, frame.columns.get_loc('Open')] = 104.8
            frame.iloc[pivot_index, frame.columns.get_loc('Close')] = 104.2
            frame.iloc[pivot_index + 1, frame.columns.get_loc('Low')] = 100.5
    frame.iloc[80, frame.columns.get_loc('Open')] = 99.0
    frame.iloc[80, frame.columns.get_loc('High')] = 101.0
    frame.iloc[80, frame.columns.get_loc('Low')] = 97.8
    frame.iloc[80, frame.columns.get_loc('Close')] = 99.7
    return frame


def _mirrored_price_frame() -> pd.DataFrame:
    frame = _price_frame()
    mirrored = frame.copy()
    mirrored['Open'] = 200.0 - frame['Open']
    mirrored['High'] = 200.0 - frame['Low']
    mirrored['Low'] = 200.0 - frame['High']
    mirrored['Close'] = 200.0 - frame['Close']
    return mirrored


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        opened_at=pd.Timestamp('2025-01-01 06:40', tz='UTC'),
        closed_at=pd.Timestamp('2025-01-01 06:45', tz='UTC'),
        open=99.0,
        high=100.2,
        low=98.5,
        close=99.7,
        atr=2.0,
        rsi=50.0,
        bollinger_upper=105.0,
        bollinger_lower=95.0,
        previous_high_20=101.0,
        previous_low_20=98.8,
        environment_side='SELL',
        filter_label=FilterLabel.SHORT,
        context_1h_closed_at=pd.Timestamp('2025-01-01 06:00', tz='UTC'),
        context_4h_closed_at=pd.Timestamp('2025-01-01 04:00', tz='UTC'),
    )


def test_key_level_v2_finds_repeated_reaction_zone() -> None:
    frame = _price_frame()

    candidates = build_key_level_candidates(frame)

    candidate = candidates.loc[frame.index[80]]
    assert candidate['side'] == 'BUY'
    assert int(candidate['touch_count']) >= 3
    assert float(candidate['reaction_atr']) >= 0.8
    assert candidate['trigger'] in {'REJECTION', 'FALSE_BREAK'}
    assert int(candidate['score']) >= 5
    assert float(candidate['target_zone_lower']) > frame.iloc[80]['High']
    current_atr = float(atr_wilder(frame['High'], frame['Low'], frame['Close'], 14).iloc[80])
    assert float(candidate['stop_price']) == pytest.approx(
        min(float(candidate['zone_lower']), frame.iloc[80]['Low'])
        - current_atr * STOP_BUFFER_ATR_MULTIPLE
    )
    assert float(candidate['target_price']) == pytest.approx(
        float(candidate['target_zone_lower']) - current_atr * TARGET_BUFFER_ATR_MULTIPLE
    )
    assert float(candidate['reward_risk']) >= MIN_REWARD_RISK


def test_key_level_v2_finds_lower_target_for_short_candidate() -> None:
    frame = _mirrored_price_frame()

    candidate = build_key_level_candidates(frame).loc[frame.index[80]]

    assert candidate['side'] == 'SELL'
    assert float(candidate['target_zone_upper']) < frame.iloc[80]['Low']
    assert float(candidate['target_price']) < frame.iloc[80]['Close']


def test_key_level_v2_rejects_candidate_without_target_or_after_costs() -> None:
    assert build_key_level_candidates(_price_frame(include_target=False)).empty
    assert build_key_level_candidates(_price_frame(), taker_fee=0.1).empty


@pytest.mark.parametrize('mutation', ['reversed', 'duplicated'])
def test_key_level_v2_rejects_noncausal_time_index(mutation: str) -> None:
    frame = _price_frame()
    if mutation == 'reversed':
        invalid = frame.iloc[::-1]
    else:
        invalid = pd.concat([frame.iloc[:1], frame])

    with pytest.raises(ValueError, match='strictly increasing and unique'):
        build_key_level_candidates(invalid)


def test_key_level_v2_does_not_skip_a_near_low_reward_target_for_farther_zone() -> None:
    frame = _price_frame()
    for pivot_index in (20, 35, 50, 65):
        frame.iloc[pivot_index + 1, frame.columns.get_loc('High')] = 103.5

    candidates = build_key_level_candidates(frame)

    assert frame.index[80] not in candidates.index


def test_key_level_v2_selects_nearest_when_multiple_target_zones_qualify() -> None:
    def high_members(price: float) -> list[key_level_v2.ConfirmedPivot]:
        return [
            key_level_v2.ConfirmedPivot(index, index + 2, price, 1.0, 'HIGH')
            for index in (2, 8, 14)
        ]

    near = (104.8, 105.2, high_members(105.0))
    far = (109.8, 110.2, high_members(110.0))
    target = key_level_v2._nearest_target_zone(
        side='BUY',
        entry_zone_lower=98.0,
        entry_zone_upper=99.0,
        zones=[far, near],
        bar_index=20,
        current_atr=1.0,
        highs=np.full(21, 100.0),
        lows=np.full(21, 100.0),
    )

    assert target is not None
    assert target.lower == 104.8
    assert target.upper == 105.2


def test_structural_reward_risk_includes_slippage_and_two_sided_fees() -> None:
    gross = structural_reward_risk(
        side='BUY',
        reference_price=100.0,
        stop_price=98.0,
        target_price=104.0,
        taker_fee=0.0,
        slippage_rate=0.0,
    )
    after_costs = structural_reward_risk(
        side='BUY',
        reference_price=100.0,
        stop_price=98.0,
        target_price=104.0,
        taker_fee=0.0005,
        slippage_rate=0.0002,
    )

    assert gross == 2.0
    assert after_costs is not None
    assert after_costs < gross


def test_structural_reward_risk_short_without_costs_is_exact() -> None:
    reward_risk = structural_reward_risk(
        side='SELL',
        reference_price=100.0,
        stop_price=102.0,
        target_price=96.0,
        taker_fee=0.0,
        slippage_rate=0.0,
    )

    assert reward_risk == 2.0


@pytest.mark.parametrize(
    ('side', 'reference_price', 'stop_price', 'target_price', 'slippage_rate'),
    [
        ('BUY', 99.95, 100.0, 110.0, 0.0002),
        ('SELL', 100.05, 100.0, 90.0, 0.0002),
        ('BUY', 100.0, 90.0, 100.05, 0.001),
        ('SELL', 100.0, 110.0, 99.95, 0.001),
    ],
)
def test_structural_reward_risk_rejects_raw_or_filled_entry_outside_frozen_prices(
    side: str,
    reference_price: float,
    stop_price: float,
    target_price: float,
    slippage_rate: float,
) -> None:
    assert structural_reward_risk(
        side=side,
        reference_price=reference_price,
        stop_price=stop_price,
        target_price=target_price,
        taker_fee=0.0005,
        slippage_rate=slippage_rate,
    ) is None


def test_key_level_v2_lookback_contains_current_bar_and_previous_239(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        {
            'Open': 100.0,
            'High': 101.0,
            'Low': 99.0,
            'Close': 100.0,
        },
        index=pd.date_range('2025-01-01', periods=241, freq='5min', tz='UTC'),
    )
    pivot = key_level_v2.ConfirmedPivot(
        pivot_index=0,
        confirm_index=0,
        price=99.0,
        atr=2.0,
        kind='LOW',
    )
    seen: dict[int, tuple[int, ...]] = {}

    monkeypatch.setattr(key_level_v2, '_confirmed_pivots', lambda *_: {0: (pivot,)})

    def capture_pivots(**kwargs: object) -> None:
        bar_index = int(kwargs['bar_index'])
        pivots = kwargs['pivots']
        seen[bar_index] = tuple(item.pivot_index for item in pivots)
        return None

    monkeypatch.setattr(key_level_v2, '_best_candidate', capture_pivots)

    build_key_level_candidates(frame)

    assert seen[239] == (0,)
    assert seen[240] == ()


def test_key_level_v2_prefix_matches_full_history() -> None:
    frame = _price_frame()

    full = build_key_level_candidates(frame)
    for prefix_length in (45, 60, 75, 81, len(frame)):
        prefix = build_key_level_candidates(frame.iloc[:prefix_length])
        pd.testing.assert_frame_equal(
            full.loc[full.index <= frame.index[prefix_length - 1]],
            prefix,
            check_dtype=False,
        )


def test_key_level_v2_signal_keeps_context_as_display_only() -> None:
    signal = evaluate_manual_candidate(
        _snapshot(),
        ManualSignalMode.KEY_LEVEL_V2,
        order_flow_features={
            'side': 'BUY',
            'zone_lower': 98.4,
            'zone_upper': 99.1,
            'target_zone_lower': 104.0,
            'target_zone_upper': 104.5,
            'target_touch_count': 3,
            'target_score': 5,
            'stop_price': 97.8,
            'target_price': 103.8,
            'reward_risk': 1.7,
            'touch_count': 4,
            'reaction_atr': 1.25,
            'role_flip': True,
            'trigger': 'BREAK_RETEST',
            'score': 7,
        },
    )

    assert signal is not None
    assert signal.mode is ManualSignalMode.KEY_LEVEL_V2
    assert signal.strategy == 'KEY_LEVEL_V2'
    assert signal.side == 'BUY'
    assert signal.stop_distance == pytest.approx(1.9)
    assert signal.target_distance == pytest.approx(4.1)
    assert signal.estimated_stop_price == 97.8
    assert signal.estimated_target_price == 103.8
    assert signal.structural_risk is not None
    assert signal.structural_risk.reference_reward_risk == 1.7
    assert signal.environment_side == 'SELL'
    assert signal.filter_label is FilterLabel.SHORT
    assert '4 次独立触碰' in signal.reason
    assert '突破后回踩' in signal.reason
    assert '下一关键区域 104.00–104.50' in signal.reason


def test_key_level_v2_signal_rejects_inconsistent_structural_levels() -> None:
    with pytest.raises(ValueError, match='inconsistent'):
        evaluate_manual_candidate(
            _snapshot(),
            ManualSignalMode.KEY_LEVEL_V2,
            order_flow_features={
                'side': 'BUY',
                'zone_lower': 98.4,
                'zone_upper': 99.1,
                'target_zone_lower': 104.0,
                'target_zone_upper': 104.5,
                'target_touch_count': 3,
                'target_score': 5,
                'stop_price': 101.0,
                'target_price': 103.8,
                'reward_risk': 1.7,
                'touch_count': 4,
                'reaction_atr': 1.25,
                'role_flip': True,
                'trigger': 'BREAK_RETEST',
                'score': 7,
            },
        )
