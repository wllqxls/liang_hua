from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from src.backtest import engine as engine_module
from src.backtest.engine import BacktestEngine, _filter_recent_days, _merge_context_features
from src.strategies.signal_models import FilterLabel, MarginMode, Signal, SignalMode, SimulationTrade
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

    merged = _merge_context_features(entry, context, lookback=5)

    assert len(merged) == len(entry)
    assert "ContextTrend" in merged.columns
    assert "ContextTrendStrength" in merged.columns
    assert "ContextTrendMomentum" in merged.columns
    assert "ContextFastMA" in merged.columns
    assert "ContextSupport" in merged.columns
    assert "ContextResistance" in merged.columns
    assert merged["ContextTrend"].notna().any()
    assert merged["ContextTrendStrength"].dropna().ge(0).all()


def test_context_features_do_not_use_an_unclosed_context_candle() -> None:
    context_index = pd.date_range('2026-01-01', periods=20, freq='15min', tz='UTC')
    context = pd.DataFrame(
        {
            'Open': [100.0] * 20,
            'High': [101.0] * 20,
            'Low': [99.0] * 20,
            'Close': [100.0] * 19 + [999.0],
            'Volume': [1.0] * 20,
        },
        index=context_index,
    )
    entry_time = context_index[-1] + pd.Timedelta(minutes=5)
    entry = pd.DataFrame(
        {'Open': [1.0], 'High': [1.0], 'Low': [1.0], 'Close': [1.0], 'Volume': [1.0]},
        index=pd.DatetimeIndex([entry_time]),
    )

    merged = _merge_context_features(entry, context, lookback=5)
    baseline = _merge_context_features(entry, context.iloc[:-1], lookback=5)

    assert merged.loc[entry_time, 'ContextClose'] == 100.0
    assert merged.loc[entry_time, 'ContextTrendStrength'] == baseline.loc[
        entry_time, 'ContextTrendStrength'
    ]
    assert merged.loc[entry_time, 'ContextTrendMomentum'] == baseline.loc[
        entry_time, 'ContextTrendMomentum'
    ]
    assert merged.loc[entry_time, 'ContextFastMA'] == baseline.loc[
        entry_time, 'ContextFastMA'
    ]


def test_filter_recent_days_keeps_latest_window(sample_ohlcv: pd.DataFrame) -> None:
    filtered = _filter_recent_days(sample_ohlcv, days=2)

    assert filtered.index.min() >= sample_ohlcv.index.max() - pd.Timedelta(days=2)
    assert filtered.index.max() == sample_ohlcv.index.max()


def test_run_signal_mode_lists_every_missing_required_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc_info:
        BacktestEngine(tmp_path).run_signal_mode(
            symbol='ETH/USDT',
            timeframe='5m',
            mode=SignalMode.KEY_LEVEL,
        )

    message = str(exc_info.value)
    assert 'ETH_USDT_5m.csv' in message
    assert 'ETH_USDT_1h.csv' in message
    assert 'ETH_USDT_4h.csv' in message


def test_run_signal_mode_keeps_warmup_then_filters_requested_window(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    indices = {
        '5m': pd.date_range('2026-01-01', periods=100, freq='5min', tz='UTC'),
        '1h': pd.date_range('2025-12-20', periods=100, freq='1h', tz='UTC'),
        '4h': pd.date_range('2025-11-01', periods=100, freq='4h', tz='UTC'),
    }
    for timeframe, index in indices.items():
        pd.DataFrame(
            {'Open': 100.0, 'High': 101.0, 'Low': 99.0, 'Close': 100.0, 'Volume': 1.0},
            index=index,
        ).to_csv(tmp_path / f'BTC_USDT_{timeframe}.csv')

    captured: dict[str, Any] = {}

    def fake_build(entry: pd.DataFrame, hour: pd.DataFrame, four_hour: pd.DataFrame, *, timeframe: str) -> pd.Series:
        captured['frame_lengths'] = (len(entry), len(hour), len(four_hour))
        return pd.Series(list(entry.index), index=entry.index, dtype=object)

    class FakeSimulator:
        def run(self, snapshots: pd.Series, **kwargs: Any) -> SimpleNamespace:
            captured['snapshots'] = snapshots
            captured['kwargs'] = kwargs
            return SimpleNamespace(trades=(), equity_curve=pd.Series([100.0], index=[snapshots.index[-1]]))

    monkeypatch.setattr(engine_module, 'build_market_snapshots', fake_build)
    monkeypatch.setattr(engine_module, 'SignalSimulator', FakeSimulator)

    BacktestEngine(tmp_path).run_signal_mode(
        symbol='BTC/USDT',
        timeframe='5m',
        mode=SignalMode.KEY_LEVEL_RSI,
        backtest_days=1,
        cash=100,
        opening_amount=10,
        margin_mode=MarginMode.CROSS,
        leverage=5,
        taker_fee=0.0005,
        slippage_rate=0.0002,
        funding_rate=0.0001,
        maintenance_margin_rate=0.005,
    )

    assert captured['frame_lengths'] == (100, 100, 100)
    assert captured['snapshots'].index.min() >= indices['5m'][-1] - pd.Timedelta(days=1)
    assert captured['kwargs']['mode'] is SignalMode.KEY_LEVEL_RSI
    assert captured['kwargs']['margin_mode'] is MarginMode.CROSS
    assert captured['kwargs']['opening_amount'] == 10


def test_run_signal_mode_maps_enriched_trade_and_costs(tmp_path: Path, monkeypatch: Any) -> None:
    frequencies = {'5m': '5min', '1h': '1h', '4h': '4h'}
    for timeframe, frequency in frequencies.items():
        index = pd.date_range('2026-01-01', periods=2, freq=frequency, tz='UTC')
        pd.DataFrame(
            {'Open': 100.0, 'High': 101.0, 'Low': 99.0, 'Close': 100.0, 'Volume': 1.0},
            index=index,
        ).to_csv(tmp_path / f'BTC_USDT_{timeframe}.csv')
    signal_time = pd.Timestamp('2026-01-01 00:05', tz='UTC')
    signal = Signal(
        mode=SignalMode.RSI_REVERSAL,
        strategy='RSI_REVERSAL',
        side='BUY',
        signal_time=signal_time,
        signal_close=100,
        atr_snapshot=2,
        stop_atr_multiple=1.5,
        target_atr_multiple=2,
        stop_distance=3,
        target_distance=4,
        estimated_stop_price=97,
        estimated_target_price=104,
        environment_side='BUY',
        filter_label=FilterLabel.LONG,
        reason='test',
        score=80,
    )
    trade = SimulationTrade(
        signal=signal,
        fill_time=signal_time + pd.Timedelta(minutes=5),
        fill_price=101,
        atr_snapshot=2,
        quantity=0.5,
        opening_amount=10,
        notional_amount=50,
        leverage=5,
        margin_mode=MarginMode.ISOLATED,
        stop_price=98,
        target_price=105,
        expected_stop_amount=1.5,
        expected_target_amount=2,
        liquidation_price=81,
        exit_time=signal_time + pd.Timedelta(minutes=10),
        exit_price=105,
        exit_reason='TARGET',
        entry_commission=0.025,
        exit_commission=0.026,
        funding=-0.01,
        pnl=1.939,
        pnl_percent=19.39,
        environment_side='BUY',
        filter_label=FilterLabel.LONG,
    )

    monkeypatch.setattr(engine_module, 'build_market_snapshots', lambda *args, **kwargs: pd.Series([object()], index=[signal_time]))

    losing_trade = replace(
        trade,
        signal=replace(signal, side='SELL'),
        funding=0.02,
        pnl=-2,
        pnl_percent=-20,
        exit_reason='STOP',
    )

    class FakeSimulator:
        def run(self, snapshots: pd.Series, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                trades=(trade, losing_trade),
                equity_curve=pd.Series(
                    [100.0, 110.0, 99.0, 105.0],
                    index=pd.date_range(signal_time, periods=4, freq='5min'),
                ),
            )

    monkeypatch.setattr(engine_module, 'SignalSimulator', FakeSimulator)
    result = BacktestEngine(tmp_path).run_signal_mode(mode=SignalMode.RSI_REVERSAL)

    item = result.trade_list[0]
    assert item['mode'] == 'RSI_REVERSAL'
    assert item['strategy_source'] == 'RSI_REVERSAL'
    assert item['margin_mode'] == 'ISOLATED'
    assert item['signal_price'] == 100
    assert item['fill_price'] == 101
    assert item['environment_1h'] == 'BUY'
    assert item['filter_4h'] == 'FILTER_LONG'
    assert item['entry_commission'] == 0.025
    assert item['exit_commission'] == 0.026
    assert item['funding_fee'] == -0.01
    expected_returns = pd.Series([100.0, 110.0, 99.0, 105.0]).pct_change().dropna()
    expected_sharpe = expected_returns.mean() / expected_returns.std() * (288 * 365) ** 0.5
    assert result.total_return_pct == pytest.approx(5.0)
    assert result.win_rate_pct == pytest.approx(50.0)
    assert result.max_drawdown_pct == pytest.approx(-10.0)
    assert result.sharpe_ratio == pytest.approx(expected_sharpe)
    assert result.num_trades == 2
    assert [point['equity'] for point in result.equity_curve] == [100.0, 110.0, 99.0, 105.0]
    assert result.total_funding_fee == pytest.approx(0.01)


def test_signal_result_zero_trade_constant_equity_metrics() -> None:
    simulation = SimpleNamespace(
        trades=(),
        equity_curve=pd.Series(
            [100.0, 100.0],
            index=pd.date_range('2026-01-01', periods=2, freq='5min', tz='UTC'),
        ),
    )

    result = engine_module._map_signal_result(simulation, cash=100, timeframe='5m')

    assert result.total_return_pct == 0
    assert result.win_rate_pct == 0
    assert result.max_drawdown_pct == 0
    assert result.sharpe_ratio is None
    assert result.num_trades == 0
    assert result.total_funding_fee == 0
