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


def test_backtest_api_returns_404_for_missing_market_data(monkeypatch: Any) -> None:
    def missing(self: object, **kwargs: Any) -> BacktestResult:
        raise FileNotFoundError('回测缺少必要数据文件: BTC_USDT_4h.csv')

    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', missing)
    response = TestClient(app).post('/api/backtest', json={})

    assert response.status_code == 404
    assert 'BTC_USDT_4h.csv' in response.json()['detail']


def test_backtest_api_returns_422_without_leaking_value_error_details(monkeypatch: Any) -> None:
    def invalid(self: object, **kwargs: Any) -> BacktestResult:
        raise ValueError(r'invalid data at C:\secret\market.csv')

    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', invalid)
    response = TestClient(app).post('/api/backtest', json={})

    assert response.status_code == 422
    assert response.json()['detail'] == '回测参数或数据格式无效'
    assert 'secret' not in response.text


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
    assert 'password' not in response.text
    assert 'database password leaked' in caplog.text


def test_optimization_request_rejects_typo_and_new_backtest_fields() -> None:
    client = TestClient(app)
    routes._reset_optimization_jobs_for_tests()
    base = {
        'symbol': 'BTC/USDT',
        'timeframe': '5m',
        'context_timeframe': '15m',
        'strategy': 'KeyLevelScoring',
        'cash': 100,
        'position_amount': 10,
    }

    typo = client.post('/api/optimize/jobs', json={**base, 'positon_amount': 10})
    mixed = client.post('/api/optimize/jobs', json={**base, 'mode': 'KEY_LEVEL'})

    assert typo.status_code == 422
    assert mixed.status_code == 422


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
    assert "out_sample_return_pct" in payload["candidates"][0]
    assert "random_pass_rate_pct" in payload["candidates"][0]
    assert "robustness_score" in payload["candidates"][0]
    assert payload["evaluated_count"] < len(calls)
    assert payload["filtered_count"] == 0
    assert calls[0]["slippage_rate"] == 0.0002
    assert calls[0]["context_timeframe"] == "15m"
    assert calls[0]["context_lookback"] in routes.CONTEXT_LOOKBACK_OPTIONS
    assert calls[0]["window_start"] < calls[0]["window_end"]
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
