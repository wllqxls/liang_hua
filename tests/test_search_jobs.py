from __future__ import annotations

import threading
import time
import logging
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from src.web import routes
from src.backtest.optimizer import SearchCandidate
from src.strategies.signal_models import MarginMode, SignalMode, SignalParameters
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

    assert routes._candidate_budget_exhausted(
        0.0, attempt_count=10, duration_total=300.0, now=300.0,
    ) is True
    assert routes._candidate_budget_exhausted(
        0.0, attempt_count=100, duration_total=100.0, now=100.0,
    ) is False


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
    signal_parameters = SignalParameters(rsi_buy_threshold=35)
    candidate = SearchCandidate(
        SignalMode.KEY_LEVEL_RSI,
        '5m',
        10,
        MarginMode.CROSS,
        signal_parameters,
    )

    item, filtered, failed = routes._evaluate_progressive_candidate(
        routes.BacktestEngine(), req, candidate, {},
    )

    assert filtered is False
    assert failed is False
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
        'signal_parameters': signal_parameters,
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
    clock = {'now': 0.0}
    calls = 0

    def fake_run(self: object, **kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        clock['now'] = routes.SEARCH_HARD_LIMIT_SECONDS
        return SimpleNamespace(
            total_return_pct=12,
            win_rate_pct=60,
            max_drawdown_pct=-5,
            sharpe_ratio=1.5,
            num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: clock['now'])
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


def _run_pipeline_with_deadline_crossing_on_call(
    monkeypatch: Any,
    crossing_call: int,
) -> tuple[OptimizationResponse, list[dict[str, Any]]]:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)
    clock = {'now': 0.0}
    calls: list[dict[str, Any]] = []

    def fake_run(self: object, **kwargs: Any) -> object:
        calls.append(kwargs)
        if len(calls) == crossing_call:
            clock['now'] = routes.SEARCH_HARD_LIMIT_SECONDS
        return SimpleNamespace(
            total_return_pct=12,
            win_rate_pct=60,
            max_drawdown_pct=-5,
            sharpe_ratio=1.5,
            num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes,
        '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(
        BacktestRequest(backtest_days=60, leverage=7),
        lambda **_: None,
    )
    return response, calls


def test_oos_crossing_hard_deadline_starts_no_random_or_long_windows(
    monkeypatch: Any,
) -> None:
    response, calls = _run_pipeline_with_deadline_crossing_on_call(monkeypatch, 2)

    assert len(calls) == 2  # in-sample, OOS
    assert response.partial is True
    assert response.candidates == []


def test_first_random_crossing_hard_deadline_starts_no_second_random_or_long_window(
    monkeypatch: Any,
) -> None:
    response, calls = _run_pipeline_with_deadline_crossing_on_call(monkeypatch, 3)

    assert len(calls) == 3  # in-sample, OOS, random 1
    assert response.partial is True
    assert response.candidates == []


def test_ninety_day_crossing_hard_deadline_starts_no_180_day_window(
    monkeypatch: Any,
) -> None:
    response, calls = _run_pipeline_with_deadline_crossing_on_call(monkeypatch, 5)

    assert len(calls) == 5  # in-sample, OOS, random 1/2, 90d
    assert response.partial is True
    assert response.candidates == []


def test_candidate_does_not_start_when_data_loading_reaches_hard_deadline(
    monkeypatch: Any,
) -> None:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)
    clock = {'now': 0.0}
    calls = 0

    def load_bounds(*_: object) -> tuple[pd.Timestamp, pd.Timestamp]:
        clock['now'] = routes.SEARCH_HARD_LIMIT_SECONDS
        return pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')

    def fake_run(self: object, **kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError('candidate must not start after the hard deadline')

    monkeypatch.setattr(routes.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(routes, '_load_data_bounds', load_bounds)
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(BacktestRequest(), lambda **_: None)

    assert calls == 0
    assert response.partial is True
    assert response.candidates == []


def test_pipeline_deduplicates_same_candidate_across_stages(monkeypatch: Any) -> None:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)
    calls: list[dict[str, Any]] = []

    def fake_run(self: object, **kwargs: Any) -> object:
        calls.append(kwargs)
        return SimpleNamespace(
            total_return_pct=12, win_rate_pct=60, max_drawdown_pct=-5,
            sharpe_ratio=1.5, num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: 0.0)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [candidate])
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(BacktestRequest(backtest_days=60), lambda **_: None)

    in_sample_calls = [
        call for call in calls
        if round((call['window_end'] - call['window_start']).total_seconds() / 86400) == 42
    ]
    assert len(in_sample_calls) == 1
    assert len({(item.mode, item.timeframe, item.leverage, item.margin_mode) for item in response.candidates}) == len(response.candidates)


def test_all_candidate_failures_return_safe_failure(monkeypatch: Any, caplog: Any) -> None:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)

    def broken(self: object, **kwargs: Any) -> object:
        raise RuntimeError(r'secret C:\accounts\market.csv')

    monkeypatch.setattr(routes.time, 'monotonic', lambda: 0.0)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', broken)

    with caplog.at_level(logging.ERROR, logger=routes.__name__):
        response = routes._progressive_optimize(BacktestRequest(), lambda **_: None)

    assert response.success is False
    assert response.partial is True
    assert response.candidates == []
    assert response.evaluated_count == 0
    assert response.failure_count == 1
    assert response.error == '参数搜索执行失败，请稍后重试'
    assert 'secret' not in caplog.text
    assert 'Traceback' not in caplog.text
    assert 'event=optimizer_candidate_failed exception_type=RuntimeError' in caplog.text


def test_mixed_candidate_failure_returns_only_successes(monkeypatch: Any) -> None:
    candidates = [
        SearchCandidate(SignalMode.RSI_REVERSAL, '5m', 7, MarginMode.CROSS),
        SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS),
    ]

    def fake_run(self: object, **kwargs: Any) -> object:
        if kwargs['mode'] is SignalMode.RSI_REVERSAL:
            raise RuntimeError('private path')
        return SimpleNamespace(
            total_return_pct=12, win_rate_pct=60, max_drawdown_pct=-5,
            sharpe_ratio=1.5, num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: 0.0)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: candidates)
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(BacktestRequest(backtest_days=60), lambda **_: None)

    assert response.success is True
    assert response.partial is True
    assert response.failure_count == 1
    assert response.evaluated_count > 0
    assert {item.mode for item in response.candidates} == {SignalMode.KEY_LEVEL}


@pytest.mark.parametrize('failing_call', [2, 3, 5])
def test_required_validation_exception_removes_candidate(
    monkeypatch: Any,
    failing_call: int,
) -> None:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)
    calls = 0

    def fake_run(self: object, **kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        if calls == failing_call:
            raise RuntimeError('secret validation path')
        return SimpleNamespace(
            total_return_pct=12, win_rate_pct=60, max_drawdown_pct=-5,
            sharpe_ratio=1.5, num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: 0.0)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(BacktestRequest(backtest_days=60), lambda **_: None)

    assert response.success is False
    assert response.partial is True
    assert response.failure_count == 1
    assert response.candidates == []


def test_rejected_out_of_sample_result_never_enters_final_ranking(monkeypatch: Any) -> None:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 125, MarginMode.CROSS)
    calls = 0

    def fake_run(self: object, **kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        rejected = calls == 2
        return SimpleNamespace(
            total_return_pct=-95 if rejected else 500,
            win_rate_pct=5 if rejected else 80,
            max_drawdown_pct=-99 if rejected else -2,
            sharpe_ratio=-5 if rejected else 5,
            num_trades=8,
            trade_list=([{'pnl': -10}] * 8 if rejected else [{'pnl': 10}] * 8),
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: 0.0)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(BacktestRequest(backtest_days=60), lambda **_: None)

    assert response.candidates == []


def test_out_of_sample_reject_grade_is_a_hard_gate(monkeypatch: Any) -> None:
    result = SimpleNamespace(total_return_pct=1)
    monkeypatch.setattr(routes, '_run_candidate_window', lambda *_: result)
    monkeypatch.setattr(
        routes,
        '_assess_backtest_quality',
        lambda **_: routes.QualityReport(
            score=40,
            grade='reject',
            label='不建议',
            reasons=['低质量'],
            profit_factor=1.1,
            avg_win_loss_ratio=1.0,
            max_consecutive_losses=1,
            passes_filter=True,
        ),
    )
    item = {
        'mode': SignalMode.KEY_LEVEL,
        'timeframe': '5m',
        'margin_mode': MarginMode.CROSS,
        'leverage': 7,
    }

    report, calls, failed = routes._validate_candidate(
        routes.BacktestEngine(),
        BacktestRequest(),
        item,
        pd.Timestamp('2025-05-01'),
        pd.Timestamp('2025-06-01'),
        30,
        pd.Timestamp('2025-01-01'),
        pd.Timestamp('2025-07-01'),
        lambda: False,
    )

    assert calls == 1
    assert failed is False
    assert report is not None
    assert report.passes_filter is False
    assert report.robustness_label == '不稳'


def test_progress_budget_uses_real_stage_two_bound_and_only_refines_down(monkeypatch: Any) -> None:
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)
    totals: list[int] = []

    monkeypatch.setattr(routes.time, 'monotonic', lambda: 0.0)
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: [candidate])
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(
        routes.BacktestEngine, 'run_signal_mode',
        lambda *_args, **_kwargs: SimpleNamespace(
            total_return_pct=12, win_rate_pct=60, max_drawdown_pct=-5,
            sharpe_ratio=1.5, num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        ),
    )

    routes._progressive_optimize(
        BacktestRequest(backtest_days=60),
        lambda **values: totals.append(int(values['total_budget'])),
    )

    assert totals == sorted(totals, reverse=True)
    assert max(totals) <= 1 + 2 + routes.VALIDATION_BUDGET
    assert routes._new_optimization_job('budget')['total_budget'] == routes.SEARCH_TOTAL_BUDGET


def test_background_job_failure_is_generic_and_does_not_leak_secret(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    routes._reset_optimization_jobs_for_tests()
    job_id = 'safe-job'
    with routes._optimization_jobs_lock:
        routes._optimization_jobs[job_id] = routes._new_optimization_job(job_id)

    monkeypatch.setattr(
        routes, '_progressive_optimize',
        lambda *_: (_ for _ in ()).throw(RuntimeError(r'secret C:\users\key.txt')),
    )
    with caplog.at_level(logging.ERROR, logger=routes.__name__):
        routes._run_optimization_job(job_id, BacktestRequest())

    status = routes._optimization_jobs[job_id]
    assert status['success'] is False
    assert status['state'] == 'failed'
    assert status['error'] == '参数搜索执行失败，请稍后重试'
    assert 'secret' not in caplog.text
    assert 'Traceback' not in caplog.text
    assert 'event=optimizer_job_failed exception_type=RuntimeError' in caplog.text


def test_candidate_data_bounds_failure_is_safely_counted(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (_ for _ in ()).throw(OSError(r'secret C:\market.csv')),
    )
    candidate = SearchCandidate(SignalMode.KEY_LEVEL, '5m', 7, MarginMode.CROSS)

    with caplog.at_level(logging.ERROR, logger=routes.__name__):
        item, filtered, failed = routes._evaluate_progressive_candidate(
            routes.BacktestEngine(), BacktestRequest(), candidate, {},
        )

    assert item is None
    assert filtered is False
    assert failed is True
    assert 'secret' not in caplog.text


def test_long_window_data_bounds_failure_marks_validation_incomplete(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (_ for _ in ()).throw(OSError('private path')),
    )
    item = {
        'mode': SignalMode.KEY_LEVEL,
        'timeframe': '5m',
        'margin_mode': MarginMode.CROSS,
        'leverage': 7,
    }

    _, _, calls, completed, failed = routes._long_window_validation(
        routes.BacktestEngine(), BacktestRequest(), item, lambda: False,
    )

    assert calls == 0
    assert completed is False
    assert failed is True


def _run_four_candidate_pipeline(
    monkeypatch: Any,
    *,
    fail_long_leverages: set[float] | None = None,
    deadline_long_leverage: float | None = None,
) -> tuple[OptimizationResponse, list[tuple[float, int]]]:
    candidates = [
        SearchCandidate(SignalMode.KEY_LEVEL, '5m', leverage, MarginMode.CROSS)
        for leverage in [10, 7, 5, 3]
    ]
    clock = {'now': 0.0}
    long_calls: list[tuple[float, int]] = []
    failing = fail_long_leverages or set()

    def fake_run(self: object, **kwargs: Any) -> object:
        days = round((kwargs['window_end'] - kwargs['window_start']).total_seconds() / 86400)
        leverage = float(kwargs['leverage'])
        if days in {90, 180}:
            long_calls.append((leverage, days))
            if leverage in failing:
                raise RuntimeError('long validation failed')
            if leverage == deadline_long_leverage:
                clock['now'] = routes.SEARCH_HARD_LIMIT_SECONDS
        return SimpleNamespace(
            total_return_pct=leverage + 10,
            win_rate_pct=60,
            max_drawdown_pct=-5,
            sharpe_ratio=1.5,
            num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: candidates)
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(
        BacktestRequest(backtest_days=60),
        lambda **_: None,
    )
    return response, long_calls


def test_long_validation_backfills_rank_four_when_rank_two_fails(monkeypatch: Any) -> None:
    response, long_calls = _run_four_candidate_pipeline(
        monkeypatch,
        fail_long_leverages={7},
    )

    assert [item.leverage for item in response.candidates[:3]] == [10, 5, 3]
    assert all(item.long_window_days > 0 for item in response.candidates[:3])
    assert [leverage for leverage, days in long_calls if days == 90] == [10, 7, 5, 3]
    assert response.partial is True


def test_continuous_long_failures_leave_no_unvalidated_recommendations(
    monkeypatch: Any,
) -> None:
    response, long_calls = _run_four_candidate_pipeline(
        monkeypatch,
        fail_long_leverages={10, 7, 5, 3},
    )

    assert len(long_calls) == 4
    assert response.candidates == []
    assert response.success is False
    assert response.partial is True


def test_deadline_during_backfill_returns_only_completed_long_candidates(
    monkeypatch: Any,
) -> None:
    response, long_calls = _run_four_candidate_pipeline(
        monkeypatch,
        deadline_long_leverage=7,
    )

    assert long_calls == [(10.0, 90), (10.0, 180), (7.0, 90)]
    assert [item.leverage for item in response.candidates] == [10]
    assert response.candidates[0].long_window_days > 0
    assert response.partial is True


def test_slow_failed_attempts_shrink_candidate_budget(monkeypatch: Any) -> None:
    candidates = [
        SearchCandidate(SignalMode.KEY_LEVEL, '5m', leverage, MarginMode.CROSS)
        for leverage in [1, 2, 3, 5, 7, 10]
    ]
    clock = {'now': 0.0}
    in_sample_attempts = 0

    def fake_run(self: object, **kwargs: Any) -> object:
        nonlocal in_sample_attempts
        days = round((kwargs['window_end'] - kwargs['window_start']).total_seconds() / 86400)
        clock['now'] += 100.0
        if days == 42:
            in_sample_attempts += 1
            if in_sample_attempts <= 2:
                raise RuntimeError('slow failure')
        return SimpleNamespace(
            total_return_pct=12, win_rate_pct=60, max_drawdown_pct=-5,
            sharpe_ratio=1.5, num_trades=8,
            trade_list=[{'pnl': value} for value in [2, -1, 2, -1, 2, -1, 2, -1]],
        )

    monkeypatch.setattr(routes.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(routes, 'available_entry_timeframes', lambda *_: ['5m'])
    monkeypatch.setattr(routes, 'build_stage_one_candidates', lambda **_: candidates)
    monkeypatch.setattr(routes, 'build_stage_two_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        routes, '_load_data_bounds',
        lambda *_: (pd.Timestamp('2025-01-01'), pd.Timestamp('2025-07-01')),
    )
    monkeypatch.setattr(routes.BacktestEngine, 'run_signal_mode', fake_run)

    response = routes._progressive_optimize(
        BacktestRequest(backtest_days=60),
        lambda **_: None,
    )

    assert in_sample_attempts == 3
    assert response.evaluated_count == 3  # candidate + OOS + first random succeeded
    assert response.failure_count == 2
    assert response.partial is True
