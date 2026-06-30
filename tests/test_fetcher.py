from __future__ import annotations

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
