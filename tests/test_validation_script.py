from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pandas as pd
import pytest

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
        '最大回撤达到或超过 30%',
        'Profit Factor 低于 1.05',
        '年化交易次数少于 50',
    ]
    return
    assert reasons == [
        '平均窗口收益不为正',
        '最差窗口收益不高于 -40%',
        '全年收益不为正',
        '最大回撤不小于 30%',
        'Profit Factor 低于 1.05',
        '年化交易次数少于 50',
    ]


def test_validation_windows_do_not_share_inclusive_boundaries() -> None:
    windows = validate_strategies._non_overlapping_windows(
        end_time=pd.Timestamp('2026-01-01 00:00:00+00:00'),
        count=3,
        days=30,
        timeframe='5m',
    )

    ordered = sorted(windows)
    for previous, current in zip(ordered, ordered[1:]):
        assert previous[1] == current[0] - pd.Timedelta(minutes=5)
        assert previous[1] < current[0]


def test_validation_requires_exact_365_day_contract(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='365'):
        validate_strategies.run_validation_matrix(
            symbol='ETH/USDT',
            days=180,
            output_path=tmp_path / 'strategy-validation.md',
        )


def test_default_data_dir_is_project_root_based(monkeypatch: Any, tmp_path: Path) -> None:
    captured: dict[str, Path | tuple[pd.Timestamp, pd.Timestamp]] = {}

    def fake_materialize(data_dir: Path, **_: Any) -> Path:
        captured['materialize_input'] = data_dir
        return data_dir

    class FakeEngine:
        def __init__(self, data_dir: str | Path) -> None:
            captured['data_dir'] = Path(data_dir)

        def load_data(self, filepath: Path) -> pd.DataFrame:
            return _frame('2024-12-01', '2026-01-01')

        def run_signal_mode(self, **kwargs: Any) -> BacktestResult:
            return _result()

    monkeypatch.setattr(validate_strategies, 'BacktestEngine', FakeEngine)
    monkeypatch.setattr(
        validate_strategies,
        '_materialize_validation_data_dir',
        fake_materialize,
    )

    validate_strategies.run_validation_matrix(
        symbol='ETH/USDT',
        days=365,
        output_path=tmp_path / 'strategy-validation.md',
    )

    assert captured['materialize_input'] == validate_strategies.PROJECT_ROOT / 'data'
    assert captured['data_dir'] == validate_strategies.PROJECT_ROOT / 'data'


def test_preflight_requires_entry_1h_and_4h_coverage(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    _frame('2024-12-01', '2026-01-01').to_csv(data_dir / 'ETH_USDT_5m.csv')
    _frame('2024-12-01', '2026-01-01').to_csv(data_dir / 'ETH_USDT_1h.csv')
    _frame('2025-12-01', '2026-01-01').to_csv(data_dir / 'ETH_USDT_4h.csv')

    with pytest.raises(ValueError, match='ETH/USDT 4h'):
        validate_strategies.run_validation_matrix(
            symbol='ETH/USDT',
            days=365,
            output_path=tmp_path / 'strategy-validation.md',
            data_dir=data_dir,
        )


def test_preflight_rejects_data_starting_at_annual_start_without_warmup(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    end_time = pd.Timestamp('2026-01-01 00:00:00+00:00')
    annual_start = end_time - pd.Timedelta(days=365) + pd.Timedelta(minutes=5)
    for timeframe in ['5m', '1h', '4h']:
        _frame(annual_start, end_time).to_csv(data_dir / f'ETH_USDT_{timeframe}.csv')

    with pytest.raises(ValueError) as exc_info:
        validate_strategies.run_validation_matrix(
            symbol='ETH/USDT',
            days=365,
            output_path=tmp_path / 'strategy-validation.md',
            data_dir=data_dir,
        )

    message = str(exc_info.value)
    assert 'ETH/USDT 5m' in message
    assert '2024-12-27T00:05:00+00:00' in message


def test_run_validation_matrix_covers_each_mode_once_and_writes_markdown(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeEngine:
        def __init__(self, data_dir: str | Path) -> None:
            self.data_dir = Path(data_dir)

        def load_data(self, filepath: Path) -> pd.DataFrame:
            return _frame('2024-12-01', '2026-01-01')

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
    diagnostics_output = tmp_path / 'strategy-diagnostics.md'
    diagnostics_json = tmp_path / 'strategy-diagnostics.json'
    progress_updates: list[dict[str, object]] = []

    rows = validate_strategies.run_validation_matrix(
        symbol='ETH/USDT',
        days=365,
        output_path=output,
        diagnostics_output_path=diagnostics_output,
        diagnostics_json_path=diagnostics_json,
        progress=lambda **values: progress_updates.append(values),
    )

    assert len(rows) == 3
    assert output.exists()
    content = output.read_text(encoding='utf-8')
    assert '| Mode | Status |' in content
    assert content.count('| KEY_LEVEL |') == 1
    assert '- Margin baseline: `ISOLATED`' in content
    assert '通过' in content
    diagnostics_content = diagnostics_output.read_text(encoding='utf-8')
    assert '# Strategy Failure Diagnostics' in diagnostics_content
    assert '| Mode | Trades | Win Rate % |' in diagnostics_content
    assert 'Pre-fee PnL (slippage included)' in diagnostics_content
    assert 'KEY_LEVEL_RSI 相比 KEY_LEVEL' in diagnostics_content
    assert '组合模式没有形成实质性的交易筛选' in diagnostics_content
    assert '### Exit Reason' in diagnostics_content
    payload = json.loads(diagnostics_json.read_text(encoding='utf-8'))
    assert payload['success'] is True
    assert payload['symbol'] == 'ETH/USDT'
    assert payload['passed_count'] == 3
    assert payload['total_count'] == 3
    assert len(payload['summary']) == 3
    assert payload['summary'][0]['mode'] == 'KEY_LEVEL'
    assert payload['summary'][0]['findings']
    assert [item['completed'] for item in progress_updates] == [1, 2, 3]
    assert all(item['total'] == 3 for item in progress_updates)
    assert all(row.status == '通过' for row in rows)
    assert len(calls) == 3 * 13

    grouped: dict[tuple[SignalMode, MarginMode], list[dict[str, Any]]] = {}
    for call in calls:
        grouped.setdefault((call['mode'], call['margin_mode']), []).append(call)

    assert set(grouped) == {
        (mode, MarginMode.ISOLATED)
        for mode in SignalMode
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
        assert all(
            call['taker_fee'] == validate_strategies.VALIDATION_TAKER_FEE
            for call in group_calls
        )
        assert all(
            call['slippage_rate'] == validate_strategies.VALIDATION_SLIPPAGE_RATE
            for call in group_calls
        )
        assert all(
            call['funding_rate'] == validate_strategies.VALIDATION_FUNDING_RATE
            for call in group_calls
        )
        ordered = sorted(window_calls, key=lambda item: item['window_start'])
        for previous, current in zip(ordered, ordered[1:]):
            assert previous['window_end'] < current['window_start']


def test_run_validation_matrix_uses_yearly_data_directories(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    data_dir = tmp_path / 'data'
    for year in ['2025', '2026']:
        (data_dir / year).mkdir(parents=True)
    for timeframe in ['5m', '1h', '4h']:
        _frame('2025-01-01', '2025-12-31 23:55').to_csv(
            data_dir / '2025' / f'ETH_USDT_{timeframe}.csv'
        )
        _frame('2026-01-01', '2026-07-11 13:55').to_csv(
            data_dir / '2026' / f'ETH_USDT_{timeframe}.csv'
        )

    captured: dict[str, Path] = {}

    class FakeEngine:
        def __init__(self, data_dir: str | Path) -> None:
            captured['data_dir'] = Path(data_dir)

        def load_data(self, filepath: Path) -> pd.DataFrame:
            frame = pd.read_csv(filepath, index_col=0, parse_dates=True)
            captured[filepath.name] = (frame.index.min(), frame.index.max())
            return frame

        def run_signal_mode(self, **kwargs: Any) -> BacktestResult:
            return _result()

    monkeypatch.setattr(validate_strategies, 'BacktestEngine', FakeEngine)

    rows = validate_strategies.run_validation_matrix(
        symbol='ETH/USDT',
        days=365,
        output_path=tmp_path / 'strategy-validation.md',
        data_dir=data_dir,
    )

    assert len(rows) == 3
    assert captured['data_dir'] != data_dir
    for timeframe in ['5m', '1h', '4h']:
        assert captured[f'ETH_USDT_{timeframe}.csv'] == (
            pd.Timestamp('2025-01-01 00:00:00+00:00'),
            pd.Timestamp('2026-07-11 13:55:00+00:00'),
        )


def _result() -> BacktestResult:
    return BacktestResult(
        total_return_pct=12.0,
        win_rate_pct=55.0,
        max_drawdown_pct=-8.0,
        sharpe_ratio=1.2,
        num_trades=60,
        equity_curve=[],
        trade_list=[
            {'pnl': 2.0},
            {'pnl': -1.0},
            {'pnl': 1.0},
        ],
    )


def _frame(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DataFrame:
    index = pd.DatetimeIndex([_utc(start), _utc(end)])
    return pd.DataFrame(
        {
            'Open': [100.0, 101.0],
            'High': [101.0, 102.0],
            'Low': [99.0, 100.0],
            'Close': [100.5, 101.5],
            'Volume': [10.0, 11.0],
        },
        index=index,
    )


def _utc(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize('UTC')
    return timestamp.tz_convert('UTC')
