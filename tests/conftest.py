from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Return deterministic OHLCV data for offline tests."""
    index = pd.date_range(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        periods=80,
        freq="h",
        name="timestamp",
    )
    close = [100 + i * 0.8 for i in range(len(index))]
    return pd.DataFrame(
        {
            "Open": [price - 0.2 for price in close],
            "High": [price + 1.0 for price in close],
            "Low": [price - 1.0 for price in close],
            "Close": close,
            "Volume": [10.0 + i for i in range(len(index))],
        },
        index=index,
    )
