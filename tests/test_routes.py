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
        assert kwargs["leverage"] == 5
        assert kwargs["take_profit_amount"] == 0
        assert kwargs["stop_loss_amount"] == 2
        assert kwargs["commission"] == 0.0005
        return BacktestResult(
            total_return_pct=12.5,
            win_rate_pct=50.0,
            max_drawdown_pct=-3.2,
            sharpe_ratio=1.1,
            num_trades=2,
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
            "strategy": "SRBreakout",
            "lookback": 20,
            "cash": 100_000,
            "position_amount": 3.3,
            "leverage": 5,
            "take_profit_amount": 0,
            "stop_loss_amount": 2,
            "maker_fee": 0.0002,
            "taker_fee": 0.0005,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total_return_pct"] == 12.5
    assert payload["equity_curve"][0]["equity"] == 100_000.0


def test_index_renders_chinese_strategy_names() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
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
            "strategy": "SRBreakout",
            "lookback": 20,
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
            "strategy": "SRBreakout",
            "lookback": 20,
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
