from dataclasses import FrozenInstanceError, replace

import numpy as np
import pandas as pd
import pytest

from src.strategies.signal_evaluators import evaluate_key_level, evaluate_rsi_reversal
from src.strategies.signal_models import (
    FilterLabel,
    MarketSnapshot,
    SignalMode,
    SignalParameters,
)


BASE = MarketSnapshot(
    opened_at=pd.Timestamp('2026-01-01 00:00', tz='UTC'),
    closed_at=pd.Timestamp('2026-01-01 00:05', tz='UTC'),
    open=100,
    high=101,
    low=99,
    close=100,
    atr=10,
    rsi=50,
    bollinger_upper=110,
    bollinger_lower=90,
    previous_high_20=105,
    previous_low_20=95,
    environment_side='BUY',
    filter_label=FilterLabel.SHORT,
    context_1h_closed_at=pd.Timestamp('2026-01-01 00:00', tz='UTC'),
    context_4h_closed_at=pd.Timestamp('2026-01-01 00:00', tz='UTC'),
)


def test_rsi_buy_builds_frozen_signal_from_close_and_atr_snapshot() -> None:
    signal = evaluate_rsi_reversal(
        replace(BASE, rsi=24.9, low=89, close=91),
        SignalMode.KEY_LEVEL_RSI,
    )

    assert signal is not None
    assert signal.mode is SignalMode.KEY_LEVEL_RSI
    assert signal.strategy == 'RSI_REVERSAL'
    assert signal.side == 'BUY'
    assert signal.signal_time == BASE.closed_at
    assert signal.signal_close == 91
    assert signal.atr_snapshot == 10
    assert (signal.stop_atr_multiple, signal.target_atr_multiple) == (0.6, 1.2)
    assert (signal.stop_distance, signal.target_distance) == (6, 12)
    assert (signal.estimated_stop_price, signal.estimated_target_price) == (85, 103)
    assert signal.environment_side == 'BUY'
    assert signal.filter_label is FilterLabel.SHORT
    assert signal.score == 3
    with pytest.raises(FrozenInstanceError):
        signal.score = 4  # type: ignore[misc]


def test_rsi_sell_builds_prices_in_the_short_direction() -> None:
    signal = evaluate_rsi_reversal(
        replace(
            BASE,
            rsi=75.1,
            high=111,
            close=109,
            environment_side='SELL',
            filter_label=FilterLabel.LONG,
        ),
        SignalMode.RSI_REVERSAL,
    )

    assert signal is not None
    assert signal.side == 'SELL'
    assert (signal.estimated_stop_price, signal.estimated_target_price) == (115, 97)
    assert signal.filter_label is FilterLabel.LONG
    assert signal.score == 3


@pytest.mark.parametrize(
    'changes',
    [
        {'rsi': 25},
        {'low': 90.1},
        {'close': 90},
        {'environment_side': 'SELL'},
        {'environment_side': None},
    ],
)
def test_rsi_buy_rejects_each_missing_condition(changes: dict[str, object]) -> None:
    snapshot = replace(BASE, **({'rsi': 24.9, 'low': 89, 'close': 91} | changes))

    assert evaluate_rsi_reversal(snapshot, SignalMode.RSI_REVERSAL) is None


@pytest.mark.parametrize(
    'changes',
    [
        {'rsi': 75},
        {'high': 109.9},
        {'close': 110},
        {'environment_side': 'BUY'},
        {'environment_side': None},
    ],
)
def test_rsi_sell_rejects_each_missing_condition(changes: dict[str, object]) -> None:
    snapshot = replace(
        BASE,
        **(
            {
                'rsi': 75.1,
                'high': 111,
                'close': 109,
                'environment_side': 'SELL',
            }
            | changes
        ),
    )

    assert evaluate_rsi_reversal(snapshot, SignalMode.RSI_REVERSAL) is None


def test_bollinger_touch_allows_equality_but_reclaim_is_strict() -> None:
    buy = evaluate_rsi_reversal(
        replace(BASE, rsi=24, low=90, close=90.1),
        SignalMode.RSI_REVERSAL,
    )
    sell = evaluate_rsi_reversal(
        replace(BASE, rsi=76, high=110, close=109.9, environment_side='SELL'),
        SignalMode.RSI_REVERSAL,
    )

    assert buy is not None
    assert sell is not None


def test_rsi_score_is_recorded_but_does_not_gate_entry() -> None:
    signal = evaluate_rsi_reversal(
        replace(BASE, rsi=24.99, low=90, close=90.01),
        SignalMode.RSI_REVERSAL,
    )

    assert signal is not None
    assert signal.score == 3


def test_rsi_reversal_accepts_custom_thresholds_and_risk_multiples() -> None:
    parameters = SignalParameters(
        rsi_buy_threshold=35,
        rsi_sell_threshold=65,
        rsi_stop_atr_multiple=1.1,
        rsi_target_atr_multiple=2.4,
    )

    signal = evaluate_rsi_reversal(
        replace(BASE, rsi=34.9, low=89, close=91),
        SignalMode.RSI_REVERSAL,
        parameters=parameters,
    )

    assert signal is not None
    assert (signal.stop_atr_multiple, signal.target_atr_multiple) == (1.1, 2.4)
    assert (signal.stop_distance, signal.target_distance) == (11, 24)
    assert (signal.estimated_stop_price, signal.estimated_target_price) == (80, 115)


def test_key_level_buy_and_sell_use_false_break_directions() -> None:
    buy = evaluate_key_level(
        replace(BASE, low=94, close=96, environment_side='BUY'),
        SignalMode.KEY_LEVEL,
    )
    sell = evaluate_key_level(
        replace(BASE, high=106, close=104, environment_side='SELL'),
        SignalMode.KEY_LEVEL_RSI,
    )

    assert buy is not None
    assert sell is not None
    assert (buy.mode, buy.strategy, buy.side, buy.score) == (
        SignalMode.KEY_LEVEL,
        'KEY_LEVEL',
        'BUY',
        8,
    )
    assert (sell.mode, sell.strategy, sell.side, sell.score) == (
        SignalMode.KEY_LEVEL_RSI,
        'KEY_LEVEL',
        'SELL',
        8,
    )
    assert (buy.stop_distance, buy.target_distance) == (8, 15)
    assert (buy.estimated_stop_price, buy.estimated_target_price) == (88, 111)
    assert (sell.estimated_stop_price, sell.estimated_target_price) == (112, 89)


def test_key_level_accepts_custom_risk_multiples() -> None:
    parameters = SignalParameters(
        key_stop_atr_multiple=1.3,
        key_target_atr_multiple=2.6,
    )

    signal = evaluate_key_level(
        replace(BASE, low=94, close=96, environment_side='BUY'),
        SignalMode.KEY_LEVEL,
        parameters=parameters,
    )

    assert signal is not None
    assert (signal.stop_atr_multiple, signal.target_atr_multiple) == (1.3, 2.6)
    assert (signal.stop_distance, signal.target_distance) == (13, 26)
    assert (signal.estimated_stop_price, signal.estimated_target_price) == (83, 122)


@pytest.mark.parametrize(
    'changes',
    [
        {'low': 95},
        {'close': 95},
        {'environment_side': 'SELL'},
        {'environment_side': None},
    ],
)
def test_key_level_buy_rejects_each_missing_condition(changes: dict[str, object]) -> None:
    snapshot = replace(
        BASE,
        **({'low': 94, 'close': 96, 'environment_side': 'BUY'} | changes),
    )

    assert evaluate_key_level(snapshot, SignalMode.KEY_LEVEL) is None


@pytest.mark.parametrize(
    'changes',
    [
        {'high': 105},
        {'close': 105},
        {'environment_side': 'BUY'},
        {'environment_side': None},
    ],
)
def test_key_level_sell_rejects_each_missing_condition(changes: dict[str, object]) -> None:
    snapshot = replace(
        BASE,
        **({'high': 106, 'close': 104, 'environment_side': 'SELL'} | changes),
    )

    assert evaluate_key_level(snapshot, SignalMode.KEY_LEVEL) is None


@pytest.mark.parametrize('invalid_side', ['LONG', '', 1])
@pytest.mark.parametrize('evaluator', [evaluate_rsi_reversal, evaluate_key_level])
def test_evaluators_defensively_reject_invalid_environment_side(
    invalid_side: object,
    evaluator: object,
) -> None:
    snapshot = replace(
        BASE,
        rsi=24,
        low=89,
        close=96,
        environment_side=invalid_side,  # type: ignore[arg-type]
    )

    assert evaluator(snapshot, SignalMode.KEY_LEVEL_RSI) is None  # type: ignore[operator]


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('atr', np.nan),
        ('atr', np.inf),
        ('close', -np.inf),
        ('rsi', np.nan),
        ('bollinger_lower', np.inf),
        ('bollinger_upper', -np.inf),
        ('previous_low_20', np.nan),
        ('previous_high_20', np.inf),
    ],
)
@pytest.mark.parametrize('evaluator', [evaluate_rsi_reversal, evaluate_key_level])
def test_evaluators_defensively_reject_non_finite_snapshot_values(
    field: str,
    value: float,
    evaluator: object,
) -> None:
    snapshot = replace(
        BASE,
        **({'rsi': 24, 'low': 89, 'close': 96} | {field: value}),
    )

    assert evaluator(snapshot, SignalMode.KEY_LEVEL_RSI) is None  # type: ignore[operator]
