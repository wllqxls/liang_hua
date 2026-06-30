from __future__ import annotations

from typing import Any

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
            "commission": 0.001,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total_return_pct"] == 12.5
    assert payload["equity_curve"][0]["equity"] == 100_000.0
