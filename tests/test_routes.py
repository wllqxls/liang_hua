from __future__ import annotations

from pathlib import Path
from typing import Any
import logging

import pandas as pd
from fastapi.testclient import TestClient

from main import app
from src.backtest.engine import BacktestResult
from src.web import routes


def test_backtest_api_rejects_legacy_strategy_contract() -> None:
    client = TestClient(app)

    response = client.post('/api/backtest', json={'strategy': 'SRBreakout'})

    assert response.status_code == 422


def test_backtest_api_returns_engine_result(monkeypatch: Any) -> None:
    def fake_run(self: object, **kwargs: Any) -> BacktestResult:
        assert kwargs["opening_amount"] == 10
        assert kwargs["backtest_days"] == 30
        assert kwargs["mode"].value == 'KEY_LEVEL_RSI'
        assert kwargs["margin_mode"].value == 'CROSS'
        assert kwargs["leverage"] == 5
        assert kwargs["maker_fee"] == 0.0002
        assert kwargs["taker_fee"] == 0.0005
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

    monkeypatch.setattr(routes.BacktestEngine, "run_signal_mode", fake_run)
    client = TestClient(app)

    response = client.post(
        "/api/backtest",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "5m",
            "mode": "KEY_LEVEL_RSI",
            "backtest_days": 30,
            "cash": 100_000,
            "opening_amount": 10,
            "margin_mode": "CROSS",
            "leverage": 5,
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


def test_index_renders_signal_mode_names() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert [item['value'] for item in routes.MODE_OPTIONS] == [
        'KEY_LEVEL',
        'RSI_REVERSAL',
        'KEY_LEVEL_RSI',
    ]


def test_backtest_api_rejects_unsupported_entry_timeframe() -> None:
    response = TestClient(app).post('/api/backtest', json={'timeframe': '1h'})

    assert response.status_code == 422


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

    monkeypatch.setattr(routes.BacktestEngine, "run_signal_mode", fake_run)
    client = TestClient(app)

    response = client.post(
        "/api/backtest",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "15m",
            "mode": "KEY_LEVEL",
            "cash": 10,
            "opening_amount": 9,
            "leverage": 5,
            "maker_fee": 0.0002,
            "taker_fee": 0.0005,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_backtest_api_rejects_opening_amount_above_cash() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/backtest",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "5m",
            "mode": "RSI_REVERSAL",
            "cash": 10,
            "opening_amount": 20,
            "leverage": 5,
            "maker_fee": 0.0002,
            "taker_fee": 0.0005,
        },
    )

    assert response.status_code == 422
    assert "开仓金额不能大于账户总金额" in response.json()['detail']


def test_backtest_api_rejects_cash_that_cannot_cover_entry_fee() -> None:
    response = TestClient(app).post(
        '/api/backtest',
        json={'cash': 10, 'opening_amount': 10, 'leverage': 5, 'taker_fee': 0.001},
    )

    assert response.status_code == 422
    assert '开仓手续费' in response.json()['detail']


def test_backtest_api_returns_safe_404_for_missing_market_data(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    def missing(self: object, **kwargs: Any) -> BacktestResult:
        raise FileNotFoundError(r'secret path C:\accounts\BTC_USDT_4h.csv')

    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', missing)
    with caplog.at_level(logging.ERROR, logger=routes.__name__):
        response = TestClient(app).post('/api/backtest', json={'timeframe': '5m'})

    assert response.status_code == 404
    detail = response.json()['detail']
    assert '入场周期 5m' in detail
    assert '1h' in detail
    assert '4h' in detail
    assert 'secret' not in response.text
    assert 'secret' not in caplog.text
    assert 'event=backtest_data_missing' in caplog.text
    assert 'exception_type=FileNotFoundError' in caplog.text


def test_backtest_api_returns_422_without_leaking_value_error_details(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    def invalid(self: object, **kwargs: Any) -> BacktestResult:
        raise ValueError(r'invalid data at C:\secret\market.csv')

    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', invalid)
    with caplog.at_level(logging.ERROR, logger=routes.__name__):
        response = TestClient(app).post('/api/backtest', json={})

    assert response.status_code == 422
    assert response.json()['detail'] == '回测参数或数据格式无效'
    assert 'secret' not in response.text
    assert 'secret' not in caplog.text
    assert 'event=backtest_invalid_input' in caplog.text
    assert 'exception_type=ValueError' in caplog.text


def test_backtest_api_returns_generic_500_and_logs_internal_error(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    def broken(self: object, **kwargs: Any) -> BacktestResult:
        raise RuntimeError('database password leaked')

    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', broken)
    with caplog.at_level(logging.ERROR, logger=routes.__name__):
        response = TestClient(app).post('/api/backtest', json={})

    assert response.status_code == 500
    assert response.json()['detail'] == '回测服务内部错误，请稍后重试'
    assert 'database password leaked' not in response.text
    assert 'database password leaked' not in caplog.text
    assert 'event=backtest_internal_error' in caplog.text
    assert 'exception_type=RuntimeError' in caplog.text


def test_optimization_endpoint_uses_backtest_request_and_rejects_legacy_fields() -> None:
    client = TestClient(app)
    routes._reset_optimization_jobs_for_tests()
    base = {'symbol': 'BTC/USDT', 'timeframe': '5m', 'mode': 'KEY_LEVEL'}

    typo = client.post('/api/optimize/jobs', json={**base, 'positon_amount': 10})
    mixed = client.post('/api/optimize/jobs', json={**base, 'strategy': 'KeyLevelScoring'})

    assert typo.status_code == 422
    assert mixed.status_code == 422


def test_optimize_api_returns_ranked_candidates(monkeypatch: Any) -> None:
    seen: list[Any] = []

    def fake_search(req: Any, progress: Any) -> Any:
        seen.append(req)
        return routes.OptimizationResponse(success=True, candidates=[])

    monkeypatch.setattr(routes, '_progressive_optimize', fake_search)
    client = TestClient(app)

    response = client.post(
        "/api/optimize",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "5m",
            "mode": "RSI_REVERSAL",
            "backtest_days": 30,
            "cash": 100,
            "opening_amount": 3.3,
            "margin_mode": "CROSS",
            "leverage": 5,
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
    assert payload['candidates'] == []
    assert seen[0].mode.value == 'RSI_REVERSAL'
    assert seen[0].margin_mode.value == 'CROSS'


def test_optimize_api_filters_low_quality_candidates(monkeypatch: Any) -> None:
    def fake_search(req: Any, progress: Any) -> Any:
        return routes.OptimizationResponse(
            success=True, candidates=[], evaluated_count=6, filtered_count=6,
        )

    monkeypatch.setattr(routes, '_progressive_optimize', fake_search)
    client = TestClient(app)

    response = client.post(
        "/api/optimize",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "5m",
            "mode": "KEY_LEVEL",
            "backtest_days": 30,
            "cash": 100,
            "opening_amount": 3.3,
            "margin_mode": "ISOLATED",
            "leverage": 5,
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
    assert payload["evaluated_count"] == 6
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
