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


def test_backtest_api_rejects_research_only_mode() -> None:
    client = TestClient(app)

    response = client.post(
        '/api/backtest',
        json={'mode': 'PULLBACK_CONFIRMATION'},
    )

    assert response.status_code == 422


def test_backtest_api_returns_engine_result(monkeypatch: Any) -> None:
    seen_data_dirs: list[Path] = []

    original_engine = routes.BacktestEngine

    class SpyEngine(original_engine):
        def __init__(self, data_dir: str | Path = './data') -> None:
            seen_data_dirs.append(Path(data_dir))
            super().__init__(data_dir=data_dir)

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

    monkeypatch.setattr(routes, 'BacktestEngine', SpyEngine)
    monkeypatch.setattr(SpyEngine, "run_signal_mode", fake_run)
    client = TestClient(app)

    response = client.post(
        "/api/backtest",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "5m",
            "data_year": 2025,
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
    assert seen_data_dirs == [routes.PROJECT_ROOT / 'data' / '2025']


def test_index_renders_signal_mode_names() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert [item['value'] for item in routes.MODE_OPTIONS] == [
        'KEY_LEVEL',
        'RSI_REVERSAL',
        'KEY_LEVEL_RSI',
    ]
    html = response.text
    assert '<option value="KEY_LEVEL"' in html
    assert '>关键位</option>' in html
    assert '<option value="RSI_REVERSAL"' in html
    assert '>RSI 反转</option>' in html
    assert '<option value="KEY_LEVEL_RSI"' in html
    assert '>关键位 + RSI 反转</option>' in html
    assert '<option value="ISOLATED" selected>逐仓</option>' in html
    assert '<select id="strategy">' not in html


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


def test_backtest_fee_validation_does_not_call_engine(monkeypatch: Any) -> None:
    calls = 0

    def spy_run(self: object, **kwargs: Any) -> BacktestResult:
        nonlocal calls
        calls += 1
        raise AssertionError('engine must not run')

    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', spy_run)

    response = TestClient(app).post(
        '/api/backtest',
        json={'cash': 10, 'opening_amount': 10, 'leverage': 5, 'taker_fee': 0.001},
    )

    assert response.status_code == 422
    assert calls == 0


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


def test_optimize_fee_validation_does_not_call_pipeline(monkeypatch: Any) -> None:
    calls = 0

    def spy_search(req: Any, progress: Any) -> Any:
        nonlocal calls
        calls += 1
        raise AssertionError('optimizer must not run')

    monkeypatch.setattr(routes, '_progressive_optimize', spy_search)

    response = TestClient(app).post(
        '/api/optimize',
        json={'cash': 10, 'opening_amount': 10, 'leverage': 5, 'taker_fee': 0.001},
    )

    assert response.status_code == 422
    assert calls == 0


def test_progressive_optimizer_uses_selected_year_data_dir(monkeypatch: Any) -> None:
    seen_paths: list[Path] = []

    def fake_available_entry_timeframes(data_dir: Path, symbol: str) -> list[str]:
        seen_paths.append(data_dir)
        return []

    monkeypatch.setattr(routes, 'available_entry_timeframes', fake_available_entry_timeframes)

    req = routes.BacktestRequest(symbol='BTC/USDT', timeframe='5m', data_year=2025)
    response = routes._progressive_optimize(req, lambda **_: None)

    assert response.success is False
    assert seen_paths == [routes.PROJECT_ROOT / 'data' / '2025']


def test_data_status_api_reports_selected_symbol_and_year(monkeypatch: Any) -> None:
    calls: list[tuple[Path, str, int]] = []

    def fake_inspect(data_dir: str | Path, symbol: str, year: int) -> list[Any]:
        calls.append((Path(data_dir), symbol, year))
        return [
            routes.DataStatus(symbol=symbol, timeframe='5m', year=year, exists=True, rows=2),
            routes.DataStatus(symbol=symbol, timeframe='15m', year=year, exists=False),
            routes.DataStatus(symbol=symbol, timeframe='1h', year=year, exists=True, rows=1),
            routes.DataStatus(symbol=symbol, timeframe='4h', year=year, exists=False),
        ]

    monkeypatch.setattr(routes, 'inspect_year_data', fake_inspect)

    client = TestClient(app)
    response = client.get("/api/data-status?symbol=ETH/USDT&year=2025")

    assert response.status_code == 200
    payload = response.json()
    assert calls == [(routes.PROJECT_ROOT / 'data', 'ETH/USDT', 2025)]
    assert [item['timeframe'] for item in payload] == ['5m', '15m', '1h', '4h']
    assert payload[0]['year'] == 2025
    assert payload[0]['rows'] == 2


def test_data_status_api_reports_all_symbols_when_symbol_omitted(monkeypatch: Any) -> None:
    calls: list[tuple[str, int]] = []

    def fake_inspect(data_dir: str | Path, symbol: str, year: int) -> list[Any]:
        calls.append((symbol, year))
        return [
            routes.DataStatus(symbol=symbol, timeframe='5m', year=year, exists=True, rows=1),
            routes.DataStatus(symbol=symbol, timeframe='15m', year=year, exists=False),
            routes.DataStatus(symbol=symbol, timeframe='1h', year=year, exists=False),
            routes.DataStatus(symbol=symbol, timeframe='4h', year=year, exists=False),
        ]

    monkeypatch.setattr(routes, 'inspect_year_data', fake_inspect)

    response = TestClient(app).get('/api/data-status?year=2025')

    assert response.status_code == 200
    payload = response.json()
    assert calls == [(symbol, 2025) for symbol in routes.SYMBOLS]
    assert len(payload) == len(routes.SYMBOLS) * 4
    assert {item['symbol'] for item in payload} == set(routes.SYMBOLS)


def test_fetch_data_api_fetches_selected_year_all_timeframes(monkeypatch: Any) -> None:
    calls: list[tuple[str, int, Path]] = []

    def fake_fetch(symbol: str, year: int, *, data_dir: str | Path) -> list[Any]:
        calls.append((symbol, year, Path(data_dir)))
        return [
            routes.DataStatus(symbol=symbol, timeframe='5m', year=year, exists=True, rows=10),
            routes.DataStatus(symbol=symbol, timeframe='15m', year=year, exists=True, rows=4),
            routes.DataStatus(symbol=symbol, timeframe='1h', year=year, exists=True, rows=2),
            routes.DataStatus(symbol=symbol, timeframe='4h', year=year, exists=True, rows=1),
        ]

    monkeypatch.setattr(routes, 'fetch_symbol_year', fake_fetch)
    client = TestClient(app)

    response = client.post("/api/fetch-data", json={"symbol": "BTC/USDT", "year": 2025})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["symbol"] == "BTC/USDT"
    assert payload["year"] == 2025
    assert [item['timeframe'] for item in payload['items']] == ['5m', '15m', '1h', '4h']
    assert calls == [('BTC/USDT', 2025, routes.PROJECT_ROOT / 'data')]


def test_fetch_data_api_rejects_unsupported_symbol() -> None:
    client = TestClient(app)

    response = client.post("/api/fetch-data", json={"symbol": "NOT/USDT", "year": 2025})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "暂不支持" in payload["error"]


def test_fetch_data_api_rejects_legacy_single_timeframe_fields() -> None:
    response = TestClient(app).post(
        "/api/fetch-data",
        json={"symbol": "BTC/USDT", "year": 2025, "timeframe": "1h", "days": 30},
    )

    assert response.status_code == 422


def test_fetch_data_api_returns_fetch_error(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)

    def failing_fetch(symbol: str, year: int, *, data_dir: str | Path) -> list[Any]:
        raise OSError("network unavailable")

    monkeypatch.setattr(routes, "fetch_symbol_year", failing_fetch)
    client = TestClient(app)

    response = client.post("/api/fetch-data", json={"symbol": "BTC/USDT", "year": 2025})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "数据拉取失败" in payload["error"]
