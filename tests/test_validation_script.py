from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any

import pandas as pd

from scripts import validate_strategies
from src.backtest.engine import BacktestResult
from src.strategies.signal_models import MarginMode, SignalMode


def test_validation_script_can_run_from_scripts_path() -> None:
    result = subprocess.run(
        [
            sys.executable,
            'scripts/validate_strategies.py',
            '--help',
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert 'Validate stable signal strategy modes.' in result.stdout


def test_evaluate_thresholds_requires_all_validation_gates() -> None:
    metrics = {
        'avg_window_return_pct': 0.01,
        'worst_window_return_pct': -39.99,
        'annual_return_pct': 0.01,
        'max_drawdown_pct': -29.99,
        'profit_factor': 1.05,
        'annual_trades': 50,
    }

    passed, reasons = validate_strategies.evaluate_thresholds(metrics)

    assert passed is True
    assert reasons == []


def test_evaluate_thresholds_reports_each_failed_gate() -> None:
    metrics = {
        'avg_window_return_pct': 0,
        'worst_window_return_pct': -40,
        'annual_return_pct': 0,
        'max_drawdown_pct': -30,
        'profit_factor': 1.04,
        'annual_trades': 49,
    }

    passed, reasons = validate_strategies.evaluate_thresholds(metrics)

    assert passed is False
    assert reasons == [
        '平均窗口收益不为正',
        '最差窗口收益不高于 -40%',
        '全年收益不为正',
        '最大回撤不小于 30%',
        'Profit Factor 低于 1.05',
        '年化交易次数少于 50',
    ]


def test_run_validation_matrix_covers_every_mode_margin_pair_and_writes_markdown(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeEngine:
        def __init__(self, data_dir: str | Path = './data') -> None:
            self.data_dir = Path(data_dir)

        def load_data(self, filepath: Path) -> pd.DataFrame:
            end = pd.Timestamp('2026-01-01 00:00:00+00:00')
            start = end - pd.Timedelta(days=400)
            return pd.DataFrame(
                {
                    'Open': [100.0, 101.0],
                    'High': [101.0, 102.0],
                    'Low': [99.0, 100.0],
                    'Close': [100.5, 101.5],
                    'Volume': [10.0, 11.0],
                },
                index=pd.DatetimeIndex([start, end]),
            )

        def run_signal_mode(self, **kwargs: Any) -> BacktestResult:
            calls.append(kwargs)
            is_annual = kwargs['backtest_days'] == 365
            return BacktestResult(
                total_return_pct=12.0 if is_annual else 1.0,
                win_rate_pct=55.0,
                max_drawdown_pct=-8.0,
                sharpe_ratio=1.2,
                num_trades=60 if is_annual else 5,
                equity_curve=[],
                trade_list=[
                    {'pnl': 2.0},
                    {'pnl': -1.0},
                    {'pnl': 1.0},
                ],
            )

    monkeypatch.setattr(validate_strategies, 'BacktestEngine', FakeEngine)
    output = tmp_path / 'strategy-validation.md'

    rows = validate_strategies.run_validation_matrix(
        symbol='ETH/USDT',
        days=365,
        output_path=output,
    )

    assert len(rows) == 6
    assert output.exists()
    content = output.read_text(encoding='utf-8')
    assert '| Mode | Margin | Status |' in content
    assert content.count('| KEY_LEVEL |') == 2
    assert '通过' in content
    assert all(row.status == '通过' for row in rows)
    assert len(calls) == 6 * 13

    grouped: dict[tuple[SignalMode, MarginMode], list[dict[str, Any]]] = {}
    for call in calls:
        grouped.setdefault((call['mode'], call['margin_mode']), []).append(call)

    assert set(grouped) == {
        (mode, margin_mode)
        for mode in SignalMode
        for margin_mode in (MarginMode.ISOLATED, MarginMode.CROSS)
    }
    for group_calls in grouped.values():
        window_calls = [call for call in group_calls if call['backtest_days'] == 30]
        annual_calls = [call for call in group_calls if call['backtest_days'] == 365]
        assert len(window_calls) == 12
        assert len(annual_calls) == 1
        assert all(call['timeframe'] == '5m' for call in group_calls)
        assert all(call['cash'] == 100 for call in group_calls)
        assert all(call['opening_amount'] == 10 for call in group_calls)
        assert all(call['leverage'] == 5 for call in group_calls)
        ordered = sorted(window_calls, key=lambda item: item['window_start'])
        for previous, current in zip(ordered, ordered[1:]):
            assert previous['window_end'] <= current['window_start']
