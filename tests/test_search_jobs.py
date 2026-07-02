from __future__ import annotations

import threading
import time
from typing import Any

from fastapi.testclient import TestClient

from main import app
from src.web import routes
from src.web.schemas import OptimizationResponse


def _payload() -> dict[str, Any]:
    return {
        # Task 6 keeps this legacy optimizer request shape isolated from the
        # active /api/backtest contract until Task 7 replaces the optimizer.
        'symbol': 'BTC/USDT',
        'timeframe': '5m',
        'context_timeframe': '15m',
        'strategy': 'KeyLevelScoring',
        'backtest_days': 30,
        'context_lookback': 192,
        'entry_lookback': 30,
        'cash': 100,
        'position_amount': 10,
        'leverage': 5,
        'take_profit_amount': 1,
        'stop_loss_amount': 1,
    }


def test_search_job_can_be_created_and_polled(monkeypatch: Any) -> None:
    def fake_search(req: object, progress: object) -> OptimizationResponse:
        progress(stage='精搜', evaluated_count=3, total_budget=12, filtered_count=1)
        return OptimizationResponse(success=True, candidates=[], evaluated_count=3, filtered_count=1)

    monkeypatch.setattr(routes, '_progressive_optimize', fake_search)
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
    routes._reset_optimization_jobs_for_tests()
    client = TestClient(app)

    first = client.post('/api/optimize/jobs', json=_payload()).json()
    second = client.post('/api/optimize/jobs', json=_payload()).json()
    release.set()

    assert first['success'] is True
    assert second['success'] is False
    assert '已有搜索任务' in second['error']


def test_candidate_search_reserves_time_for_validation(monkeypatch: Any) -> None:
    monkeypatch.setattr(routes, 'SEARCH_SOFT_LIMIT_SECONDS', 480.0)
    monkeypatch.setattr(routes, 'SEARCH_HARD_LIMIT_SECONDS', 600.0)

    assert routes._candidate_budget_exhausted(0.0, evaluated_count=10, now=300.0) is True
    assert routes._candidate_budget_exhausted(0.0, evaluated_count=100, now=100.0) is False
