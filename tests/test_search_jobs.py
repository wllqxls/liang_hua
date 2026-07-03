from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from main import app
from src.web import routes
from src.backtest.optimizer import SearchCandidate
from src.strategies.signal_models import MarginMode, SignalMode
from src.web.schemas import BacktestRequest, OptimizationResponse


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        'symbol': 'BTC/USDT',
        'timeframe': '5m',
        'mode': 'KEY_LEVEL',
        'backtest_days': 30,
        'cash': 100,
        'opening_amount': 10,
        'margin_mode': 'CROSS',
        'leverage': 5,
    }
    payload.update(overrides)
    return payload


def test_search_job_can_be_created_and_polled(monkeypatch: Any) -> None:
    def fake_search(req: object, progress: object) -> OptimizationResponse:
        progress(stage='精搜', evaluated_count=3, total_budget=12, filtered_count=1)
        return OptimizationResponse(success=True, candidates=[], evaluated_count=3, filtered_count=1)

    monkeypatch.setattr(routes, '_progressive_optimize', fake_search)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    routes._reset_optimization_jobs_for_tests()
    client = TestClient(app)

    created = client.post('/api/optimize/jobs', json=_payload()).json()
    assert created['success'] is True

    status: dict[str, Any] = {}
    for _ in range(50):
        status = client.get(f"/api/optimize/jobs/{created['job_id']}").json()
        if status['state'] == 'completed':
            break
        time.sleep(0.01)

    assert status['state'] == 'completed'
    assert status['stage'] == '完成'
    assert status['evaluated_count'] == 3
    assert status['filtered_count'] == 1


def test_search_job_rejects_a_second_active_job(monkeypatch: Any) -> None:
    release = threading.Event()

    def blocking_search(req: object, progress: object) -> OptimizationResponse:
        progress(stage='粗筛', evaluated_count=0, total_budget=120, filtered_count=0)
        release.wait(timeout=2)
        return OptimizationResponse(success=True, candidates=[])

    monkeypatch.setattr(routes, '_progressive_optimize', blocking_search)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    routes._reset_optimization_jobs_for_tests()
    client = TestClient(app)

    first = client.post('/api/optimize/jobs', json=_payload()).json()
    second = client.post('/api/optimize/jobs', json=_payload()).json()
    release.set()

    assert first['success'] is True
    assert second['success'] is False
    assert '已有搜索任务' in second['error']


def test_search_jobs_keep_requested_margin_mode(monkeypatch: Any) -> None:
    seen: list[object] = []

    def fake_search(req: object, progress: object) -> OptimizationResponse:
        seen.append(req.margin_mode)
        return OptimizationResponse(success=True, candidates=[])

    monkeypatch.setattr(routes, '_progressive_optimize', fake_search)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    routes._reset_optimization_jobs_for_tests()
    client = TestClient(app)

    created = client.post('/api/optimize/jobs', json=_payload(margin_mode='ISOLATED')).json()
    for _ in range(50):
        status = client.get(f"/api/optimize/jobs/{created['job_id']}").json()
        if status['state'] == 'completed':
            break
        time.sleep(0.01)

    assert [mode.value for mode in seen] == ['ISOLATED']


def test_search_job_fee_validation_does_not_call_pipeline(monkeypatch: Any) -> None:
    calls = 0

    def spy_search(req: object, progress: object) -> OptimizationResponse:
        nonlocal calls
        calls += 1
        raise AssertionError('optimizer must not run')

    monkeypatch.setattr(routes, '_progressive_optimize', spy_search)
    routes._reset_optimization_jobs_for_tests()

    response = TestClient(app).post(
        '/api/optimize/jobs',
        json=_payload(cash=10, opening_amount=10, leverage=5, taker_fee=0.001),
    )

    assert response.status_code == 422
    assert calls == 0


def test_search_job_registry_keeps_only_twenty_and_evicts_oldest(monkeypatch: Any) -> None:
    routes._reset_optimization_jobs_for_tests()
    with routes._optimization_jobs_lock:
        for index in range(20):
            job_id = f'old-{index}'
            job = routes._new_optimization_job(job_id)
            job['state'] = 'completed'
            routes._optimization_jobs[job_id] = job

    class DormantThread:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def start(self) -> None:
            pass

    monkeypatch.setattr(routes.threading, 'Thread', DormantThread)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])

    created = TestClient(app).post('/api/optimize/jobs', json=_payload()).json()

    assert created['success'] is True
    with routes._optimization_jobs_lock:
        assert len(routes._optimization_jobs) == 20
        assert 'old-0' not in routes._optimization_jobs
        assert created['job_id'] in routes._optimization_jobs


def test_candidate_search_reserves_time_for_validation(monkeypatch: Any) -> None:
    monkeypatch.setattr(routes, 'SEARCH_SOFT_LIMIT_SECONDS', 480.0)
    monkeypatch.setattr(routes, 'SEARCH_HARD_LIMIT_SECONDS', 600.0)

    assert routes._candidate_budget_exhausted(0.0, evaluated_count=10, now=300.0) is True
    assert routes._candidate_budget_exhausted(0.0, evaluated_count=100, now=100.0) is False


def test_candidate_evaluation_uses_signal_engine_and_keeps_request_values_out_of_candidate(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(self: object, **kwargs: Any) -> object:
        calls.append(kwargs)
        return SimpleNamespace(
            total_return_pct=12,
            win_rate_pct=50,
            max_drawdown_pct=-5,
            sharpe_ratio=1.2,
            num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)
    monkeypatch.setattr(
        routes,
        '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-04-01')),
    )
    req = BacktestRequest(
        opening_amount=7,
        cash=80,
        margin_mode=MarginMode.CROSS,
        backtest_days=45,
        maker_fee=0.001,
        taker_fee=0.002,
        slippage_rate=0.003,
        funding_rate=0.004,
    )
    candidate = SearchCandidate(SignalMode.KEY_LEVEL_RSI, '5m', 10, MarginMode.CROSS)

    item, filtered = routes._evaluate_progressive_candidate(
        routes.BacktestEngine(), req, candidate, {},
    )

    assert filtered is False
    assert item is not None
    assert not {
        'strategy', 'context_timeframe', 'context_lookback', 'entry_lookback',
        'take_profit_amount', 'stop_loss_amount', 'opening_amount', 'cash',
        'backtest_days', 'search_backtest_days',
    } & set(item)
    assert calls == [{
        'symbol': 'BTC/USDT',
        'timeframe': '5m',
        'mode': SignalMode.KEY_LEVEL_RSI,
        'window_start': pd.Timestamp('2025-02-15 00:00:00'),
        'window_end': pd.Timestamp('2025-03-18 12:00:00'),
        'cash': 80.0,
        'opening_amount': 7.0,
        'margin_mode': MarginMode.CROSS,
        'leverage': 10,
        'maker_fee': 0.001,
        'taker_fee': 0.002,
        'slippage_rate': 0.003,
        'funding_rate': 0.004,
        'maintenance_margin_rate': 0.005,
    }]


def test_progressive_pipeline_ranks_filters_and_runs_all_validation_windows(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(self: object, **kwargs: Any) -> object:
        calls.append(kwargs)
        low_quality = kwargs['mode'] is SignalMode.RSI_REVERSAL
        leverage = float(kwargs['leverage'])
        return SimpleNamespace(
            total_return_pct=-1 if low_quality else leverage + 5,
            win_rate_pct=10 if low_quality else 60,
            max_drawdown_pct=-40 if low_quality else -5,
            sharpe_ratio=0 if low_quality else 1.5,
            num_trades=1 if low_quality else 8,
            trade_list=(
                [{'pnl': -1}]
                if low_quality
                else [{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]]
            ),
        )

    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(
        routes,
        '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.time, 'monotonic', lambda: 0.0)

    response = routes._progressive_optimize(
        BacktestRequest(
            backtest_days=60,
            cash=100,
            opening_amount=5,
            leverage=7,
            margin_mode=MarginMode.CROSS,
        ),
        lambda **_: None,
    )

    assert response.success is True
    assert response.filtered_count >= 1
    assert response.candidates
    assert response.candidates[0].leverage == 10
    assert all(candidate.margin_mode is MarginMode.CROSS for candidate in response.candidates)
    assert all(call['margin_mode'] is MarginMode.CROSS for call in calls)
    durations = [
        round((call['window_end'] - call['window_start']).total_seconds() / 86400)
        for call in calls
    ]
    assert 18 in durations  # out-of-sample window
    assert durations.count(60) >= 2  # two deterministic random windows
    assert 90 in durations
    assert 180 in durations


def test_progressive_pipeline_returns_partial_at_soft_deadline(monkeypatch: Any) -> None:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)
    clock = iter([0.0, routes.SEARCH_SOFT_LIMIT_SECONDS])
    calls = 0

    def fake_run(self: object, **kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError('candidate must not run after soft deadline')

    monkeypatch.setattr(routes.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(BacktestRequest(), lambda **_: None)

    assert response.success is True
    assert response.partial is True
    assert calls == 0


def test_progressive_pipeline_stops_before_validation_at_hard_deadline(
    monkeypatch: Any,
) -> None:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)
    clock = iter([0.0, 0.0, routes.SEARCH_HARD_LIMIT_SECONDS])
    calls = 0

    def fake_run(self: object, **kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            total_return_pct=12,
            win_rate_pct=60,
            max_drawdown_pct=-5,
            sharpe_ratio=1.5,
            num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes,
        '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(BacktestRequest(), lambda **_: None)

    assert response.success is True
    assert response.partial is True
    assert response.candidates == []
    assert calls == 1
