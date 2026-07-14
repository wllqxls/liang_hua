from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.diagnostics import (
    DiagnosticSlice,
    StrategyDiagnostics,
    analyze_trades,
)
from src.strategies.signal_models import MarginMode, SignalMode


logger = logging.getLogger(__name__)

DEFAULT_TIMEFRAME = '5m'
DEFAULT_DATA_DIR = PROJECT_ROOT / 'data'
WINDOW_COUNT = 12
WINDOW_DAYS = 30
ANNUAL_DAYS = 365
VALIDATION_TAKER_FEE = 0.0005
VALIDATION_SLIPPAGE_RATE = 0.0002
VALIDATION_FUNDING_RATE = 0.0001
ENTRY_WARMUP_BARS = 21
HOUR_WARMUP_BARS = 20
FOUR_HOUR_WARMUP_BARS = 30
MODES = (SignalMode.KEY_LEVEL, SignalMode.RSI_REVERSAL, SignalMode.KEY_LEVEL_RSI)
VALIDATION_MARGIN_MODE = MarginMode.ISOLATED
TIMEFRAME_DELTAS = {
    '5m': pd.Timedelta(minutes=5),
    '15m': pd.Timedelta(minutes=15),
}


@dataclass(frozen=True, slots=True)
class ValidationRow:
    mode: SignalMode
    margin_mode: MarginMode
    status: str
    reasons: list[str]
    avg_window_return_pct: float
    worst_window_return_pct: float
    annual_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    annual_trades: int


@dataclass(frozen=True, slots=True)
class DiagnosticRow:
    mode: SignalMode
    margin_mode: MarginMode
    diagnostics: StrategyDiagnostics


def evaluate_thresholds(metrics: Mapping[str, float]) -> tuple[bool, list[str]]:
    """Return whether one mode passes all automated execution gates."""
    reasons: list[str] = []
    if metrics['avg_window_return_pct'] <= 0:
        reasons.append('平均窗口收益不为正')
    if metrics['worst_window_return_pct'] <= -40:
        reasons.append('最差窗口收益不高于 -40%')
    if metrics['annual_return_pct'] <= 0:
        reasons.append('全年收益不为正')
    if abs(metrics['max_drawdown_pct']) >= 30:
        reasons.append('最大回撤达到或超过 30%')
    if metrics['profit_factor'] < 1.05:
        reasons.append('Profit Factor 低于 1.05')
    if metrics['annual_trades'] < 50:
        reasons.append('年化交易次数少于 50')
    return len(reasons) == 0, reasons


def run_validation_matrix(
    *,
    symbol: str,
    days: int,
    output_path: Path,
    timeframe: str = DEFAULT_TIMEFRAME,
    data_dir: Path | str | None = None,
    diagnostics_output_path: Path | None = None,
    diagnostics_json_path: Path | None = None,
    progress: Callable[..., None] | None = None,
) -> list[ValidationRow]:
    """Run every stable signal mode once with the conservative margin baseline."""
    _validate_days(days)
    resolved_data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    resolved_data_dir = _materialize_validation_data_dir(
        resolved_data_dir,
        symbol=symbol,
        timeframe=timeframe,
    )
    engine = BacktestEngine(data_dir=resolved_data_dir)
    end_time = _preflight_data_coverage(
        engine,
        resolved_data_dir,
        symbol,
        timeframe,
        days=days,
    )
    windows = _non_overlapping_windows(
        end_time=end_time,
        count=WINDOW_COUNT,
        days=WINDOW_DAYS,
        timeframe=timeframe,
    )
    annual_start = end_time - pd.Timedelta(days=days) + _timeframe_delta(timeframe)

    rows: list[ValidationRow] = []
    diagnostic_rows: list[DiagnosticRow] = []
    for mode in MODES:
        window_results = [
            engine.run_signal_mode(
                symbol=symbol,
                timeframe=timeframe,
                mode=mode,
                backtest_days=WINDOW_DAYS,
                window_start=start,
                window_end=end,
                cash=100,
                opening_amount=10,
                margin_mode=VALIDATION_MARGIN_MODE,
                leverage=5,
                taker_fee=VALIDATION_TAKER_FEE,
                slippage_rate=VALIDATION_SLIPPAGE_RATE,
                funding_rate=VALIDATION_FUNDING_RATE,
                save_result=False,
            )
            for start, end in windows
        ]
        annual_result = engine.run_signal_mode(
            symbol=symbol,
            timeframe=timeframe,
            mode=mode,
            backtest_days=days,
            window_start=annual_start,
            window_end=end_time,
            cash=100,
            opening_amount=10,
            margin_mode=VALIDATION_MARGIN_MODE,
            leverage=5,
            taker_fee=VALIDATION_TAKER_FEE,
            slippage_rate=VALIDATION_SLIPPAGE_RATE,
            funding_rate=VALIDATION_FUNDING_RATE,
            save_result=False,
        )
        metrics = _metrics(window_results, annual_result)
        passed, reasons = evaluate_thresholds(metrics)
        diagnostic_rows.append(
            DiagnosticRow(
                mode=mode,
                margin_mode=VALIDATION_MARGIN_MODE,
                diagnostics=analyze_trades(annual_result.trade_list),
            )
        )
        rows.append(
            ValidationRow(
                mode=mode,
                margin_mode=VALIDATION_MARGIN_MODE,
                status='通过' if passed else '未通过验证',
                reasons=reasons,
                avg_window_return_pct=metrics['avg_window_return_pct'],
                worst_window_return_pct=metrics['worst_window_return_pct'],
                annual_return_pct=metrics['annual_return_pct'],
                max_drawdown_pct=metrics['max_drawdown_pct'],
                profit_factor=metrics['profit_factor'],
                annual_trades=int(metrics['annual_trades']),
            )
        )
        if progress is not None:
            progress(
                completed=len(rows),
                total=len(MODES),
                mode=mode.value,
                margin_mode=VALIDATION_MARGIN_MODE.value,
            )

    rows = [_clean_validation_row(row) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_markdown(symbol, days, timeframe, rows), encoding='utf-8')
    if diagnostics_output_path is not None:
        diagnostics_output_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics_output_path.write_text(
            _render_diagnostics_markdown(
                symbol,
                days,
                timeframe,
                diagnostic_rows,
            ),
            encoding='utf-8',
        )
    if diagnostics_json_path is not None:
        diagnostics_json_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics_json_path.write_text(
            json.dumps(
                _diagnostics_payload(
                    symbol,
                    days,
                    timeframe,
                    rows,
                    diagnostic_rows,
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding='utf-8',
        )
    return rows


def _clean_validation_row(row: ValidationRow) -> ValidationRow:
    return ValidationRow(
        mode=row.mode,
        margin_mode=row.margin_mode,
        status='通过' if not row.reasons else '未通过验证',
        reasons=row.reasons,
        avg_window_return_pct=row.avg_window_return_pct,
        worst_window_return_pct=row.worst_window_return_pct,
        annual_return_pct=row.annual_return_pct,
        max_drawdown_pct=row.max_drawdown_pct,
        profit_factor=row.profit_factor,
        annual_trades=row.annual_trades,
    )


def _materialize_validation_data_dir(
    data_dir: Path,
    *,
    symbol: str,
    timeframe: str,
) -> Path:
    safe_symbol = symbol.replace('/', '_')
    required_timeframes = (timeframe, '1h', '4h')
    sources_by_timeframe = {
        required_timeframe: _data_sources(data_dir, safe_symbol, required_timeframe)
        for required_timeframe in required_timeframes
    }
    has_yearly_sources = any(
        source.parent != data_dir
        for sources in sources_by_timeframe.values()
        for source in sources
    )
    if not has_yearly_sources:
        return data_dir

    merged_dir = PROJECT_ROOT / 'tmp' / 'validation_data' / safe_symbol / timeframe
    merged_dir.mkdir(parents=True, exist_ok=True)
    for required_timeframe, sources in sources_by_timeframe.items():
        if not sources:
            continue
        merged = _merge_data_sources(sources)
        merged.to_csv(merged_dir / f'{safe_symbol}_{required_timeframe}.csv')
    return merged_dir


def _data_sources(data_dir: Path, safe_symbol: str, timeframe: str) -> list[Path]:
    direct = data_dir / f'{safe_symbol}_{timeframe}.csv'
    sources = [direct] if direct.exists() else []
    if not data_dir.exists():
        return sources
    for child in sorted(data_dir.iterdir()):
        if not child.is_dir() or not child.name.isdigit():
            continue
        yearly = child / f'{safe_symbol}_{timeframe}.csv'
        if yearly.exists():
            sources.append(yearly)
    return sources


def _merge_data_sources(sources: Sequence[Path]) -> pd.DataFrame:
    frames = [
        pd.read_csv(source, index_col=0, parse_dates=True)
        for source in sources
    ]
    merged = pd.concat(frames)
    merged = merged.loc[~merged.index.duplicated(keep='last')]
    return merged.sort_index()


def _validate_days(days: int) -> None:
    if days != ANNUAL_DAYS:
        raise ValueError('strategy validation requires exactly one 365-day annual window')


def _preflight_data_coverage(
    engine: BacktestEngine,
    data_dir: Path,
    symbol: str,
    timeframe: str,
    *,
    days: int,
) -> pd.Timestamp:
    safe_symbol = symbol.replace('/', '_')
    frames: dict[str, pd.DataFrame] = {}
    required_timeframes = (timeframe, '1h', '4h')
    for required_timeframe in required_timeframes:
        path = data_dir / f'{safe_symbol}_{required_timeframe}.csv'
        frame = engine.load_data(path)
        if frame.empty:
            raise ValueError(f'{symbol} {required_timeframe} 数据为空，无法验证')
        frames[required_timeframe] = frame

    end_time = _as_utc_timestamp(frames[timeframe].index.max())
    annual_start = end_time - pd.Timedelta(days=days) + _timeframe_delta(timeframe)
    required_start = annual_start - _warmup_duration(timeframe)
    for required_timeframe, frame in frames.items():
        start_time = _as_utc_timestamp(frame.index.min())
        if start_time > required_start:
            raise ValueError(
                f'{symbol} {required_timeframe} 本地数据历史不足，'
                f'需要覆盖 warmup 到 {required_start.isoformat()}，实际从 {start_time.isoformat()} 开始'
            )
    return end_time


def _non_overlapping_windows(
    *,
    end_time: pd.Timestamp,
    count: int,
    days: int,
    timeframe: str,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    step = _timeframe_delta(timeframe)
    final_start = end_time - pd.Timedelta(days=days) + step
    start_time = final_start - pd.Timedelta(days=(count - 1) * days)
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for index in range(count):
        start = start_time + pd.Timedelta(days=index * days)
        end = start + pd.Timedelta(days=days) - step
        windows.append((start, end))
    return windows


def _timeframe_delta(timeframe: str) -> pd.Timedelta:
    try:
        return TIMEFRAME_DELTAS[timeframe]
    except KeyError as exc:
        raise ValueError('timeframe must be 5m or 15m') from exc


def _warmup_duration(timeframe: str) -> pd.Timedelta:
    return max(
        ENTRY_WARMUP_BARS * _timeframe_delta(timeframe),
        HOUR_WARMUP_BARS * pd.Timedelta(hours=1),
        FOUR_HOUR_WARMUP_BARS * pd.Timedelta(hours=4),
    )


def _as_utc_timestamp(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize('UTC')
    return timestamp.tz_convert('UTC')


def _metrics(
    window_results: Sequence[BacktestResult],
    annual_result: BacktestResult,
) -> dict[str, float]:
    window_returns = [float(result.total_return_pct) for result in window_results]
    return {
        'avg_window_return_pct': _average(window_returns),
        'worst_window_return_pct': min(window_returns) if window_returns else 0.0,
        'annual_return_pct': float(annual_result.total_return_pct),
        'max_drawdown_pct': float(annual_result.max_drawdown_pct),
        'profit_factor': _profit_factor(annual_result.trade_list),
        'annual_trades': float(annual_result.num_trades),
    }


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _profit_factor(trades: Sequence[Mapping[str, object]]) -> float:
    wins = 0.0
    losses = 0.0
    for trade in trades:
        pnl = float(trade.get('pnl') or 0.0)
        if pnl > 0:
            wins += pnl
        elif pnl < 0:
            losses += abs(pnl)
    if wins <= 0:
        return 0.0
    if losses <= 0:
        return 99.0
    return wins / losses


def _render_markdown(
    symbol: str,
    days: int,
    timeframe: str,
    rows: Sequence[ValidationRow],
) -> str:
    clean_lines = [
        '# Strategy Validation',
        '',
        f'- Symbol: `{symbol}`',
        f'- Timeframe: `{timeframe}`',
        f'- Annual window: `{days}` days',
        f'- Rolling windows: `{WINDOW_COUNT}` non-overlapping `{WINDOW_DAYS}`-day windows',
        f'- Margin baseline: `{VALIDATION_MARGIN_MODE.value}`',
        '',
        (
            '未通过验证的模式保持不可用于未来自动化 testnet 执行；'
            '只有状态为 `通过` 的模式可进入后续自动化模拟盘流程。'
        ),
        '',
        '| Mode | Status | Avg 30d Return % | Worst 30d Return % | Annual Return % | Max Drawdown % | Profit Factor | Annual Trades | Reasons |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        reasons = '；'.join(row.reasons) if row.reasons else '全部阈值通过'
        clean_lines.append(
            '| '
            f'{row.mode.value} | '
            f'{row.status} | '
            f'{row.avg_window_return_pct:.2f} | '
            f'{row.worst_window_return_pct:.2f} | '
            f'{row.annual_return_pct:.2f} | '
            f'{row.max_drawdown_pct:.2f} | '
            f'{row.profit_factor:.2f} | '
            f'{row.annual_trades} | '
            f'{reasons} |'
        )
    clean_lines.append('')
    return '\n'.join(clean_lines)


def _render_diagnostics_markdown(
    symbol: str,
    days: int,
    timeframe: str,
    rows: Sequence[DiagnosticRow],
) -> str:
    lines = [
        '# Strategy Failure Diagnostics',
        '',
        f'- Symbol: `{symbol}`',
        f'- Timeframe: `{timeframe}`',
        f'- Annual window: `{days}` days',
        '- Initial cash: `100 USDT`',
        '- Opening margin: `10 USDT`',
        '- Leverage: `5x`',
        f'- Margin baseline: `{VALIDATION_MARGIN_MODE.value}`',
        f'- Taker fee: `{VALIDATION_TAKER_FEE:.4%}` per fill',
        f'- Slippage: `{VALIDATION_SLIPPAGE_RATE:.4%}` per fill',
        f'- Funding rate: `{VALIDATION_FUNDING_RATE:.4%}` per 8 hours',
        '',
        (
            '本报告复用验证矩阵的同一次年度回测。手续费/资金费前收益由逐笔净收益加回手续费、'
            '扣除资金费净现金流得到，其中已经包含滑点影响；资金费为正表示账户收到，负数表示账户支付。'
        ),
        '',
        '## Summary',
        '',
        '| Mode | Trades | Win Rate % | Pre-fee PnL (slippage included) | Commission | Funding Cash Flow | Net Fee/Funding Cost | Net PnL | Pre-fee PF | Net PF | Avg Net/Trade | Fee/Funding Cost to Pre-fee Gross Profit % |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        item = row.diagnostics
        lines.append(
            '| '
            f'{row.mode.value} | '
            f'{item.trades} | '
            f'{item.win_rate_pct:.2f} | '
            f'{item.gross_pnl:.4f} | '
            f'{item.commission:.4f} | '
            f'{item.funding_cash_flow:.4f} | '
            f'{item.net_cost:.4f} | '
            f'{item.net_pnl:.4f} | '
            f'{item.gross_profit_factor:.2f} | '
            f'{item.net_profit_factor:.2f} | '
            f'{item.average_net_pnl:.4f} | '
            f'{_optional_percent(item.cost_to_gross_profit_pct)} |'
        )

    lines.extend(['', '## Cross-mode Findings', ''])
    lines.extend(f'- {finding}' for finding in _cross_mode_findings(rows))

    for row in rows:
        item = row.diagnostics
        lines.extend(
            [
                '',
                f'## {row.mode.value}',
                '',
            ]
        )
        lines.extend(f'- {finding}' for finding in _diagnostic_findings(item))
        lines.extend(
            _render_breakdown('Exit Reason', item.by_exit_reason)
            + _render_breakdown('Side', item.by_side)
            + _render_breakdown('1h Environment', item.by_environment_1h)
            + _render_breakdown('4h Filter', item.by_filter_4h)
        )
    lines.append('')
    return '\n'.join(lines)


def _diagnostics_payload(
    symbol: str,
    days: int,
    timeframe: str,
    validation_rows: Sequence[ValidationRow],
    diagnostic_rows: Sequence[DiagnosticRow],
) -> dict[str, object]:
    validation_by_key = {
        (row.mode, row.margin_mode): row
        for row in validation_rows
    }
    summary: list[dict[str, object]] = []
    for row in diagnostic_rows:
        validation = validation_by_key[(row.mode, row.margin_mode)]
        item = row.diagnostics
        summary.append(
            {
                'mode': row.mode.value,
                'margin_mode': row.margin_mode.value,
                'status': validation.status,
                'reasons': validation.reasons,
                'avg_window_return_pct': validation.avg_window_return_pct,
                'worst_window_return_pct': validation.worst_window_return_pct,
                'annual_return_pct': validation.annual_return_pct,
                'max_drawdown_pct': validation.max_drawdown_pct,
                'profit_factor': validation.profit_factor,
                'annual_trades': validation.annual_trades,
                'win_rate_pct': item.win_rate_pct,
                'pre_fee_pnl': item.gross_pnl,
                'commission': item.commission,
                'funding_cash_flow': item.funding_cash_flow,
                'net_fee_funding_cost': item.net_cost,
                'net_pnl': item.net_pnl,
                'pre_fee_profit_factor': item.gross_profit_factor,
                'average_net_pnl': item.average_net_pnl,
                'cost_to_pre_fee_gross_profit_pct': item.cost_to_gross_profit_pct,
                'findings': _diagnostic_findings(item),
            }
        )
    return {
        'success': True,
        'available': True,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'symbol': symbol,
        'timeframe': timeframe,
        'days': days,
        'passed_count': sum(not row.reasons for row in validation_rows),
        'total_count': len(validation_rows),
        'settings': {
            'cash': 100,
            'opening_amount': 10,
            'leverage': 5,
            'taker_fee': VALIDATION_TAKER_FEE,
            'slippage_rate': VALIDATION_SLIPPAGE_RATE,
            'funding_rate': VALIDATION_FUNDING_RATE,
        },
        'cross_mode_findings': _cross_mode_findings(diagnostic_rows),
        'summary': summary,
    }


def _render_breakdown(
    title: str,
    slices: Sequence[DiagnosticSlice],
) -> list[str]:
    lines = [
        '',
        f'### {title}',
        '',
        '| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    if not slices:
        lines.append('| No trades | 0 | 0.00 | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.0000 |')
        return lines
    for item in slices:
        lines.append(
            '| '
            f'{item.label} | '
            f'{item.trades} | '
            f'{item.win_rate_pct:.2f} | '
            f'{item.gross_pnl:.4f} | '
            f'{item.net_cost:.4f} | '
            f'{item.net_pnl:.4f} | '
            f'{item.profit_factor:.2f} | '
            f'{item.average_net_pnl:.4f} |'
        )
    return lines


def _diagnostic_findings(item: StrategyDiagnostics) -> list[str]:
    if item.trades == 0:
        return ['年度窗口没有产生交易，无法评估信号质量。']

    findings: list[str] = []
    if item.gross_pnl < 0:
        findings.append(
            f'在计入滑点、但尚未扣除手续费和资金费时已亏损 {abs(item.gross_pnl):.4f} USDT，'
            '说明进出场结构在真实成交条件下没有足够优势，失败不只由手续费造成。'
        )
    elif item.net_pnl < 0:
        findings.append(
            f'成本前盈利 {item.gross_pnl:.4f} USDT，但净成本 {item.net_cost:.4f} USDT '
            '将结果转为亏损，策略利润垫不足。'
        )
    else:
        findings.append(
            f'成本前收益 {item.gross_pnl:.4f} USDT，成本后净收益 {item.net_pnl:.4f} USDT。'
        )

    findings.append(
        f'{item.trades} 笔交易共产生 {item.commission:.4f} USDT 手续费，'
        f'平均每笔净收益 {item.average_net_pnl:.4f} USDT。'
    )
    if item.trades > ANNUAL_DAYS:
        findings.append(
            f'日均交易 {item.trades / ANNUAL_DAYS:.2f} 笔，交易频率较高，'
            '手续费会被持续放大。'
        )
    if item.cost_to_gross_profit_pct is not None:
        findings.append(
            '手续费与资金费净成本占手续费前盈利交易总额的 '
            f'{item.cost_to_gross_profit_pct:.2f}%。'
        )
    stop = _slice_by_label(item.by_exit_reason, 'STOP')
    target = _slice_by_label(item.by_exit_reason, 'TARGET')
    if stop is not None or target is not None:
        findings.append(
            f'止损 {stop.trades if stop else 0} 笔、止盈 {target.trades if target else 0} 笔；'
            f'止损桶净收益 {stop.net_pnl if stop else 0.0:.4f} USDT，'
            f'止盈桶净收益 {target.net_pnl if target else 0.0:.4f} USDT。'
        )
    worst_filter = _worst_losing_slice(item.by_filter_4h)
    if worst_filter is not None:
        findings.append(
            f'4 小时环境中 `{worst_filter.label}` 亏损最多：'
            f'{worst_filter.trades} 笔合计 {worst_filter.net_pnl:.4f} USDT。'
        )
    worst_side = _worst_losing_slice(item.by_side)
    if worst_side is not None:
        findings.append(
            f'方向上 `{worst_side.label}` 亏损最多：'
            f'{worst_side.trades} 笔合计 {worst_side.net_pnl:.4f} USDT。'
        )
    return findings


def _cross_mode_findings(rows: Sequence[DiagnosticRow]) -> list[str]:
    indexed = {row.mode: row.diagnostics for row in rows}
    findings: list[str] = []
    key = indexed.get(SignalMode.KEY_LEVEL)
    combined = indexed.get(SignalMode.KEY_LEVEL_RSI)
    if key is not None and combined is not None and key.trades > 0:
        trade_change_pct = (combined.trades - key.trades) / key.trades * 100
        message = (
            'KEY_LEVEL_RSI 相比 KEY_LEVEL 的交易数变化 '
            f'{trade_change_pct:+.2f}%（{key.trades} -> {combined.trades}），'
            f'净收益变化 {combined.net_pnl - key.net_pnl:+.4f} USDT。'
        )
        if abs(trade_change_pct) <= 5:
            message += '组合模式没有形成实质性的交易筛选。'
        findings.append(message)
    return findings or ['没有足够的跨模式数据可比较。']


def _slice_by_label(
    slices: Sequence[DiagnosticSlice],
    label: str,
) -> DiagnosticSlice | None:
    return next((item for item in slices if item.label == label), None)


def _worst_losing_slice(
    slices: Sequence[DiagnosticSlice],
) -> DiagnosticSlice | None:
    losing = [item for item in slices if item.net_pnl < 0]
    return min(losing, key=lambda item: item.net_pnl) if losing else None


def _optional_percent(value: float | None) -> str:
    return '-' if value is None else f'{value:.2f}'


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Validate stable signal strategy modes.')
    parser.add_argument('--symbol', default='ETH/USDT')
    parser.add_argument('--days', type=int, default=365)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnostics-output', type=Path)
    parser.add_argument('--diagnostics-json', type=Path)
    parser.add_argument('--timeframe', default=DEFAULT_TIMEFRAME, choices=['5m', '15m'])
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = _parse_args()
    rows = run_validation_matrix(
        symbol=args.symbol,
        days=args.days,
        output_path=args.output,
        timeframe=args.timeframe,
        diagnostics_output_path=(
            args.diagnostics_output
            if args.diagnostics_output is not None
            else args.output.with_name('strategy-diagnostics.md')
        ),
        diagnostics_json_path=(
            args.diagnostics_json
            if args.diagnostics_json is not None
            else PROJECT_ROOT / 'results' / 'strategy-diagnostics.json'
        ),
    )
    passed = sum(1 for row in rows if not row.reasons)
    logger.info('validation rows=%s passed=%s output=%s', len(rows), passed, args.output)


if __name__ == '__main__':
    main()
