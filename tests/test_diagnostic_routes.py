from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from main import app
from scripts import validate_strategies
from src.web import routes
from src.web.schemas import DiagnosticRequest


class _DeferredThread:
    def __init__(self, **kwargs: Any) -> None:
        self.target = kwargs['target']
        self.args = kwargs['args']

    def start(self) -> None:
        return None


def test_latest_diagnostics_returns_unavailable_without_json(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        routes,
        'DIAGNOSTICS_JSON_PATH',
        tmp_path / 'missing.json',
    )

    response = TestClient(app).get('/api/diagnostics/latest')

    assert response.status_code == 200
    assert response.json() == {
        'success': True,
        'available': False,
        'summary': [],
        'cross_mode_findings': [],
    }


def test_latest_diagnostics_returns_structured_json(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    path = tmp_path / 'strategy-diagnostics.json'
    path.write_text(
        json.dumps(
            {
                'success': True,
                'available': True,
                'symbol': 'ETH/USDT',
                'summary': [{'mode': 'KEY_LEVEL'}],
            }
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(routes, 'DIAGNOSTICS_JSON_PATH', path)

    payload = TestClient(app).get('/api/diagnostics/latest').json()

    assert payload['available'] is True
    assert payload['symbol'] == 'ETH/USDT'
    assert payload['summary'][0]['mode'] == 'KEY_LEVEL'


def test_create_diagnostic_job_is_background_and_singleton(monkeypatch: Any) -> None:
    routes._reset_diagnostic_jobs_for_tests()
    monkeypatch.setattr(routes.threading, 'Thread', _DeferredThread)
    client = TestClient(app)

    created = client.post(
        '/api/diagnostics/jobs',
        json={'symbol': 'ETH/USDT', 'timeframe': '5m'},
    ).json()
    duplicate = client.post(
        '/api/diagnostics/jobs',
        json={'symbol': 'ETH/USDT', 'timeframe': '5m'},
    ).json()

    assert created['success'] is True
    assert created['job_id']
    assert duplicate == {
        'success': False,
        'job_id': None,
        'error': '已有策略诊断正在运行，请等待完成',
    }


def test_diagnostic_job_reports_progress_and_completion(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    routes._reset_diagnostic_jobs_for_tests()
    job_id = 'diagnostic-job'
    with routes._diagnostic_jobs_lock:
        routes._diagnostic_jobs[job_id] = routes._new_diagnostic_job(job_id)

    json_path = tmp_path / 'strategy-diagnostics.json'
    monkeypatch.setattr(routes, 'DIAGNOSTICS_JSON_PATH', json_path)

    def fake_validation(**kwargs: Any) -> list[Any]:
        kwargs['progress'](
            completed=2,
            total=3,
            mode='RSI_REVERSAL',
            margin_mode='ISOLATED',
        )
        Path(kwargs['diagnostics_json_path']).write_text(
            '{"success": true, "available": true}',
            encoding='utf-8',
        )
        return []

    monkeypatch.setattr(validate_strategies, 'run_validation_matrix', fake_validation)

    routes._run_diagnostic_job(
        job_id,
        DiagnosticRequest(symbol='ETH/USDT', timeframe='5m'),
    )

    job = routes._diagnostic_jobs[job_id]
    assert job['success'] is True
    assert job['state'] == 'completed'
    assert job['completed_count'] == 3
    assert job['stage'] == '完成'


def test_diagnostic_job_status_recomputes_elapsed_time(monkeypatch: Any) -> None:
    routes._reset_diagnostic_jobs_for_tests()
    job_id = 'elapsed-job'
    with routes._diagnostic_jobs_lock:
        job = routes._new_diagnostic_job(job_id)
        job['_started_at'] = 100.0
        routes._diagnostic_jobs[job_id] = job
    monkeypatch.setattr(routes.time, 'monotonic', lambda: 112.3)

    payload = TestClient(app).get(
        f'/api/diagnostics/jobs/{job_id}'
    ).json()

    assert payload['elapsed_seconds'] == 12.3


def test_diagnostic_job_failure_is_safe(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    routes._reset_diagnostic_jobs_for_tests()
    job_id = 'failed-job'
    with routes._diagnostic_jobs_lock:
        routes._diagnostic_jobs[job_id] = routes._new_diagnostic_job(job_id)

    def broken(**_: Any) -> list[Any]:
        raise RuntimeError('secret token from private path')

    monkeypatch.setattr(validate_strategies, 'run_validation_matrix', broken)
    with caplog.at_level(logging.ERROR, logger=routes.__name__):
        routes._run_diagnostic_job(
            job_id,
            DiagnosticRequest(symbol='ETH/USDT', timeframe='5m'),
        )

    job = routes._diagnostic_jobs[job_id]
    assert job['success'] is False
    assert job['state'] == 'failed'
    assert job['error'] == '策略诊断执行失败，请稍后重试'
    assert 'secret token' not in caplog.text
    assert 'event=diagnostics_job_failed' in caplog.text


def test_diagnostic_request_rejects_unknown_symbol() -> None:
    response = TestClient(app).post(
        '/api/diagnostics/jobs',
        json={'symbol': 'UNKNOWN/USDT', 'timeframe': '5m'},
    )

    assert response.status_code == 422
    assert response.json()['detail'] == '不支持的交易对象'
