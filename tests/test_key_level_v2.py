import numpy as np
import pandas as pd

from src.strategies.key_level_v2 import build_key_level_candidates
from src.strategies.manual_candidates import evaluate_manual_candidate
from src.strategies.signal_models import FilterLabel, ManualSignalMode, MarketSnapshot


def _price_frame(rows: int = 90) -> pd.DataFrame:
    index = pd.date_range('2025-01-01', periods=rows, freq='5min', tz='UTC')
    base = np.linspace(0.0, 0.15, rows)
    frame = pd.DataFrame(
        {
            'Open': 100.0 + base,
            'High': 100.8 + base,
            'Low': 99.2 + base,
            'Close': 100.1 + base,
            'Volume': 1000.0,
        },
        index=index,
    )
    for pivot_index in (20, 35, 50, 65):
        frame.iloc[pivot_index, frame.columns.get_loc('Low')] = 98.8
        frame.iloc[pivot_index, frame.columns.get_loc('Open')] = 99.2
        frame.iloc[pivot_index, frame.columns.get_loc('Close')] = 99.6
        frame.iloc[pivot_index + 1, frame.columns.get_loc('High')] = 101.4
    frame.iloc[80, frame.columns.get_loc('Open')] = 99.0
    frame.iloc[80, frame.columns.get_loc('High')] = 100.2
    frame.iloc[80, frame.columns.get_loc('Low')] = 98.5
    frame.iloc[80, frame.columns.get_loc('Close')] = 99.7
    return frame


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


def test_key_level_v2_prefix_matches_full_history() -> None:
    frame = _price_frame()

    full = build_key_level_candidates(frame)
    prefix = build_key_level_candidates(frame.iloc[:81])

    pd.testing.assert_frame_equal(full.loc[full.index <= frame.index[80]], prefix)


def test_key_level_v2_signal_keeps_context_as_display_only() -> None:
    signal = evaluate_manual_candidate(
        _snapshot(),
        ManualSignalMode.KEY_LEVEL_V2,
        order_flow_features={
            'side': 'BUY',
            'zone_lower': 98.4,
            'zone_upper': 99.1,
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
    assert signal.stop_distance == 1.6
    assert signal.target_distance == 3.0
    assert signal.environment_side == 'SELL'
    assert signal.filter_label is FilterLabel.SHORT
    assert '4 次独立触碰' in signal.reason
    assert '突破后回踩' in signal.reason
