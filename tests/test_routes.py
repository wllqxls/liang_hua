from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from main import app
from src.backtest.engine import BacktestResult
from src.web import routes


def test_backtest_api_returns_error_for_unknown_strategy() -> None:
    client = TestClient(app)

    response = client.post("/api/backtest", json={"strategy": "MissingStrategy"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "未知策略" in payload["error"]


def test_backtest_api_returns_engine_result(monkeypatch: Any) -> None:
    def fake_run(self: object, **kwargs: Any) -> BacktestResult:
        assert kwargs["position_amount"] == 3.3
        assert kwargs["context_timeframe"] == "15m"
        assert kwargs["context_lookback"] == 192
        assert kwargs["backtest_days"] == 30
        assert kwargs["lookback"] == 30
        assert kwargs["leverage"] == 5
        assert kwargs["take_profit_amount"] == 0
        assert kwargs["stop_loss_amount"] == 2
        assert kwargs["commission"] == 0.0005
        assert kwargs["slippage_rate"] == 0.0002
        assert kwargs["funding_rate"] == 0.0001
        assert kwargs["maintenance_margin_rate"] == 0.005
        assert kwargs["save_result"] is True
        return BacktestResult(
            total_return_pct=12.5,
            win_rate_pct=50.0,
            max_drawdown_pct=-3.2,
            sharpe_ratio=1.1,
            num_trades=2,
            total_funding_fee=0.12,
            result_path="results/demo.json",
            equity_curve=[{"timestamp": "2024-01-01T00:00:00+00:00", "equity": 100_000.0}],
            trade_list=[],
        )

    monkeypatch.setattr(routes.BacktestEngine, "run", fake_run)
    client = TestClient(app)

    response = client.post(
        "/api/backtest",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "context_timeframe": "15m",
            "strategy": "SRBreakout",
            "backtest_days": 30,
            "context_lookback": 192,
            "entry_lookback": 30,
            "cash": 100_000,
            "position_amount": 3.3,
            "leverage": 5,
            "take_profit_amount": 0,
            "stop_loss_amount": 2,
            "maker_fee": 0.0002,
            "taker_fee": 0.0005,
            "slippage_rate": 0.0002,
            "funding_rate": 0.0001,
            "maintenance_margin_rate": 0.005,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total_return_pct"] == 12.5
    assert payload["total_funding_fee"] == 0.12
    assert payload["result_path"] == "results/demo.json"
    assert payload["equity_curve"][0]["equity"] == 100_000.0


def test_index_renders_chinese_strategy_names() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "关键位评分" in response.text
    assert "支撑阻力突破" in response.text
    assert "均线金叉死叉" in response.text
    assert "RSI 超卖反弹" in response.text


def test_backtest_api_accepts_ten_usdt_cash(monkeypatch: Any) -> None:
    def fake_run(self: object, **kwargs: Any) -> BacktestResult:
        assert kwargs["cash"] == 10
        return BacktestResult(
            total_return_pct=0.0,
            win_rate_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=None,
            num_trades=0,
            equity_curve=[],
            trade_list=[],
        )

    monkeypatch.setattr(routes.BacktestEngine, "run", fake_run)
    client = TestClient(app)

    response = client.post(
        "/api/backtest",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "context_timeframe": "15m",
            "strategy": "SRBreakout",
            "backtest_days": 30,
            "context_lookback": 192,
            "entry_lookback": 30,
            "cash": 10,
            "position_amount": 3.3,
            "leverage": 5,
            "take_profit_amount": 0,
            "stop_loss_amount": 2,
            "maker_fee": 0.0002,
            "taker_fee": 0.0005,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_backtest_api_rejects_position_amount_above_cash() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/backtest",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "context_timeframe": "15m",
            "strategy": "SRBreakout",
            "backtest_days": 30,
            "context_lookback": 192,
            "entry_lookback": 30,
            "cash": 10,
            "position_amount": 20,
            "leverage": 5,
            "take_profit_amount": 0,
            "stop_loss_amount": 2,
            "maker_fee": 0.0002,
            "taker_fee": 0.0005,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "逐仓金额不能大于初始资金" in payload["error"]


def test_optimize_api_returns_ranked_candidates(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(self: object, **kwargs: Any) -> BacktestResult:
        calls.append(kwargs)
        score_base = kwargs["leverage"] + kwargs["lookback"] * 0.01
        return BacktestResult(
            total_return_pct=score_base,
            win_rate_pct=45.0,
            max_drawdown_pct=-2.0,
            sharpe_ratio=None,
            num_trades=8,
            equity_curve=[],
            trade_list=[
                {"pnl": 1.2},
                {"pnl": -0.4},
                {"pnl": 1.0},
                {"pnl": -0.3},
                {"pnl": 0.8},
                {"pnl": -0.2},
                {"pnl": 0.9},
                {"pnl": -0.2},
            ],
        )

    monkeypatch.setattr(routes.BacktestEngine, "run", fake_run)
    client = TestClient(app)

    response = client.post(
        "/api/optimize",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "context_timeframe": "15m",
            "strategy": "SRBreakout",
            "backtest_days": 30,
            "context_lookback": 192,
            "entry_lookback": 30,
            "cash": 100,
            "position_amount": 3.3,
            "leverage": 5,
            "take_profit_amount": 0,
            "stop_loss_amount": 2,
            "maker_fee": 0.0002,
            "taker_fee": 0.0005,
            "slippage_rate": 0.0002,
            "funding_rate": 0.0001,
            "maintenance_margin_rate": 0.005,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert len(payload["candidates"]) == 10
    assert payload["candidates"][0]["rank"] == 1
    assert "strategy" in payload["candidates"][0]
    assert "strategy_label" in payload["candidates"][0]
    assert "quality_score" in payload["candidates"][0]
    assert payload["evaluated_count"] == len(calls)
    assert payload["filtered_count"] == 0
    assert calls[0]["slippage_rate"] == 0.0002
    assert calls[0]["context_timeframe"] == "15m"
    assert calls[0]["context_lookback"] in routes.CONTEXT_LOOKBACK_OPTIONS
    assert calls[0]["backtest_days"] == 30
    assert all(candidate["take_profit_amount"] > 0 for candidate in payload["candidates"])
    assert all(candidate["context_lookback"] in routes.CONTEXT_LOOKBACK_OPTIONS for candidate in payload["candidates"])
    assert all(candidate["entry_lookback"] in routes.ENTRY_LOOKBACK_OPTIONS for candidate in payload["candidates"])
    assert all(candidate["leverage"] in routes.LEVERAGE_OPTIONS for candidate in payload["candidates"])
    assert all(call["take_profit_amount"] > 0 for call in calls)
    assert all(call["leverage"] in routes.LEVERAGE_OPTIONS for call in calls)
    strategy_classes = {call["strategy_class"].__name__ for call in calls}
    assert strategy_classes == {"KeyLevelScoring", "SRBreakout", "MovingAverageCross", "RSIReversion"}


def test_optimize_api_filters_low_quality_candidates(monkeypatch: Any) -> None:
    def fake_run(self: object, **kwargs: Any) -> BacktestResult:
        return BacktestResult(
            total_return_pct=80.0,
            win_rate_pct=10.0,
            max_drawdown_pct=-45.0,
            sharpe_ratio=None,
            num_trades=2,
            equity_curve=[],
            trade_list=[
                {"pnl": -0.3},
                {"pnl": 5.0},
            ],
        )

    monkeypatch.setattr(routes.BacktestEngine, "run", fake_run)
    client = TestClient(app)

    response = client.post(
        "/api/optimize",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "context_timeframe": "15m",
            "strategy": "SRBreakout",
            "backtest_days": 30,
            "context_lookback": 192,
            "entry_lookback": 30,
            "cash": 100,
            "position_amount": 3.3,
            "leverage": 5,
            "take_profit_amount": 0,
            "stop_loss_amount": 2,
            "maker_fee": 0.0002,
            "taker_fee": 0.0005,
            "slippage_rate": 0.0002,
            "funding_rate": 0.0001,
            "maintenance_margin_rate": 0.005,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["candidates"] == []
    assert payload["evaluated_count"] > 0
    assert payload["filtered_count"] == payload["evaluated_count"]


def test_data_status_api_reports_local_csv(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        {
            "timestamp": ["2024-01-01T00:00:00+00:00"],
            "Open": [1.0],
            "High": [2.0],
            "Low": [0.5],
            "Close": [1.5],
            "Volume": [10.0],
        }
    ).to_csv(data_dir / "BTC_USDT_1h.csv", index=False)

    client = TestClient(app)
    response = client.get("/api/data-status")

    assert response.status_code == 200
    payload = response.json()
    btc_1h = next(item for item in payload if item["symbol"] == "BTC/USDT" and item["timeframe"] == "1h")
    assert btc_1h["exists"] is True
    assert btc_1h["rows"] == 1


def test_fetch_data_api_saves_csv(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeFetcher:
        def fetch_and_save(self, symbol: str, timeframe: str, since: object, data_dir: str) -> Path:
            path = Path(data_dir) / f"{symbol.replace('/', '_')}_{timeframe}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {
                    "timestamp": ["2024-01-01T00:00:00+00:00", "2024-01-01T01:00:00+00:00"],
                    "Open": [1.0, 1.1],
                    "High": [2.0, 2.1],
                    "Low": [0.5, 0.6],
                    "Close": [1.5, 1.6],
                    "Volume": [10.0, 11.0],
                }
            ).to_csv(path, index=False)
            return path

    monkeypatch.setattr(routes, "DataFetcher", FakeFetcher)
    client = TestClient(app)

    response = client.post("/api/fetch-data", json={"symbol": "BTC/USDT", "timeframe": "1h", "days": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["rows"] == 2
    assert (tmp_path / "data" / "BTC_USDT_1h.csv").exists()


def test_fetch_data_api_rejects_unsupported_symbol() -> None:
    client = TestClient(app)

    response = client.post("/api/fetch-data", json={"symbol": "NOT/USDT", "timeframe": "1h", "days": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "暂不支持" in payload["error"]


def test_fetch_data_api_returns_fetch_error(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)

    class FailingFetcher:
        def fetch_and_save(self, symbol: str, timeframe: str, since: object, data_dir: str) -> Path:
            raise OSError("network unavailable")

    monkeypatch.setattr(routes, "DataFetcher", FailingFetcher)
    client = TestClient(app)

    response = client.post("/api/fetch-data", json={"symbol": "BTC/USDT", "timeframe": "1h", "days": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "数据拉取失败" in payload["error"]
