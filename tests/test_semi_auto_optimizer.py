from __future__ import annotations

import pandas as pd

from src.backtest.semi_auto_optimizer import write_semi_auto_whitelist


def test_empty_whitelist_csv_keeps_schema(tmp_path) -> None:
    destination = tmp_path / 'whitelist.csv'

    write_semi_auto_whitelist([], destination)

    frame = pd.read_csv(destination)
    assert frame.empty
    assert {'rank', 'parameters', 'events_2024', 'events_2025', 'trigger_logic'} <= set(frame.columns)
