from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine, _merge_context_features
from src.strategies.sr_breakout import SRBreakout


class FakeFetcher:
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self.calls: list[tuple[str, str]] = []

    def fetch_ohlcv(self, symbol: str, timeframe: str) -> pd.DataFrame:
        self.calls.append((symbol, timeframe))
        return self.df.copy()


class FailingFetcher:
    def fetch_ohlcv(self, symbol: str, timeframe: str) -> pd.DataFrame:
        raise ConnectionError("network unavailable")


def test_load_data_reads_local_csv(tmp_path: Path, sample_ohlcv: pd.DataFrame) -> None:
    data_file = tmp_path / "BTC_USDT_1h.csv"
    sample_ohlcv.to_csv(data_file)

    df = BacktestEngine(tmp_path).load_data(data_file)

    assert len(df) == len(sample_ohlcv)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_load_data_fetches_and_saves_missing_csv(
    tmp_path: Path,
    sample_ohlcv: pd.DataFrame,
) -> None:
    fetcher = FakeFetcher(sample_ohlcv)
    data_file = tmp_path / "ETH_USDT_4h.csv"

    df = BacktestEngine(tmp_path, fetcher=fetcher).load_data(data_file)

    assert fetcher.calls == [("ETH/USDT", "4h")]
    assert data_file.exists()
    assert len(df) == len(sample_ohlcv)


def test_load_data_wraps_fetch_failure(tmp_path: Path) -> None:
    data_file = tmp_path / "ETH_USDT_4h.csv"

    with pytest.raises(RuntimeError, match="自动拉取 ETH/USDT 4h 也失败"):
        BacktestEngine(tmp_path, fetcher=FailingFetcher()).load_data(data_file)


def test_load_data_rejects_missing_columns(tmp_path: Path) -> None:
    data_file = tmp_path / "BTC_USDT_1h.csv"
    pd.DataFrame({"Open": [1.0], "Close": [1.0]}).to_csv(data_file)

    with pytest.raises(ValueError, match="数据文件缺少必要列"):
        BacktestEngine(tmp_path).load_data(data_file)


def test_run_returns_backtest_result(tmp_path: Path, sample_ohlcv: pd.DataFrame) -> None:
    data_file = tmp_path / "BTC_USDT_1h.csv"
    sample_ohlcv.to_csv(data_file)

    result = BacktestEngine(tmp_path).run(
        SRBreakout,
        symbol="BTC/USDT",
        timeframe="1h",
        cash=100_000,
        commission=0.001,
        lookback=5,
    )

    assert isinstance(result.total_return_pct, float)
    assert isinstance(result.win_rate_pct, float)
    assert result.num_trades >= 0
    assert len(result.equity_curve) == len(sample_ohlcv)


def test_context_features_align_to_entry_timeframe(sample_ohlcv: pd.DataFrame) -> None:
    entry = sample_ohlcv.resample("15min").ffill()
    context = sample_ohlcv

    merged = _merge_context_features(entry, context)

    assert len(merged) == len(entry)
    assert "ContextTrend" in merged.columns
    assert "ContextSupport" in merged.columns
    assert "ContextResistance" in merged.columns
    assert merged["ContextTrend"].notna().any()
