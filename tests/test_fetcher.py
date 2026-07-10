from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.data.fetcher import DataFetcher


def test_load_local_reads_existing_csv(tmp_path: Path, sample_ohlcv: pd.DataFrame) -> None:
    data_file = tmp_path / "BTC_USDT_1h.csv"
    sample_ohlcv.to_csv(data_file)

    df = DataFetcher().load_local("BTC/USDT", "1h", str(tmp_path))

    assert len(df) == len(sample_ohlcv)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index.name == "timestamp"


def test_load_local_raises_for_missing_csv(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="本地数据不存在"):
        DataFetcher().load_local("ETH/USDT", "4h", str(tmp_path))


def test_fetch_ohlcv_respects_until_boundary() -> None:
    class FakeExchange:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def fetch_ohlcv(
            self,
            symbol: str,
            timeframe: str,
            *,
            since: int,
            limit: int,
        ) -> list[list[float]]:
            self.calls.append(since)
            return [
                [datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000, 1, 2, 0, 1.5, 100],
                [datetime(2025, 1, 1, 0, 5, tzinfo=timezone.utc).timestamp() * 1000, 2, 3, 1, 2.5, 100],
                [datetime(2025, 1, 1, 0, 10, tzinfo=timezone.utc).timestamp() * 1000, 3, 4, 2, 3.5, 100],
            ]

    fetcher = DataFetcher()
    fake_exchange = FakeExchange()
    fetcher.exchange = fake_exchange  # type: ignore[assignment]

    df = fetcher.fetch_ohlcv(
        symbol='ETH/USDT',
        timeframe='5m',
        since=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        until=datetime(2025, 1, 1, 0, 5, tzinfo=timezone.utc),
    )

    assert list(df.index.astype(str)) == [
        '2025-01-01 00:00:00+00:00',
        '2025-01-01 00:05:00+00:00',
    ]
    assert len(fake_exchange.calls) == 1
