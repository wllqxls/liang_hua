from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.engine import BacktestEngine, BacktestResult
from src.strategies.signal_models import MarginMode, SignalMode


logger = logging.getLogger(__name__)

DEFAULT_TIMEFRAME = '5m'
WINDOW_COUNT = 12
WINDOW_DAYS = 30
MODES = (SignalMode.KEY_LEVEL, SignalMode.RSI_REVERSAL, SignalMode.KEY_LEVEL_RSI)
MARGIN_MODES = (MarginMode.ISOLATED, MarginMode.CROSS)


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
        reasons.append('最大回撤不小于 30%')
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
    data_dir: Path | str = './data',
) -> list[ValidationRow]:
    """Run all stable signal modes across isolated and cross margin."""
    engine = BacktestEngine(data_dir=data_dir)
    end_time = _data_end_time(engine, Path(data_dir), symbol, timeframe)
    windows = _non_overlapping_windows(end_time=end_time, count=WINDOW_COUNT, days=WINDOW_DAYS)
    annual_start = end_time - pd.Timedelta(days=days)

    rows: list[ValidationRow] = []
    for mode in MODES:
        for margin_mode in MARGIN_MODES:
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
                    margin_mode=margin_mode,
                    leverage=5,
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
                margin_mode=margin_mode,
                leverage=5,
                save_result=False,
            )
            metrics = _metrics(window_results, annual_result)
            passed, reasons = evaluate_thresholds(metrics)
            rows.append(
                ValidationRow(
                    mode=mode,
                    margin_mode=margin_mode,
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_markdown(symbol, days, timeframe, rows), encoding='utf-8')
    return rows


def _data_end_time(
    engine: BacktestEngine,
    data_dir: Path,
    symbol: str,
    timeframe: str,
) -> pd.Timestamp:
    safe_symbol = symbol.replace('/', '_')
    df = engine.load_data(data_dir / f'{safe_symbol}_{timeframe}.csv')
    if df.empty:
        raise ValueError(f'{symbol} {timeframe} 数据为空，无法验证')
    end_time = pd.Timestamp(df.index.max())
    if end_time.tzinfo is None:
        return end_time.tz_localize('UTC')
    return end_time.tz_convert('UTC')


def _non_overlapping_windows(
    *,
    end_time: pd.Timestamp,
    count: int,
    days: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start_time = end_time - pd.Timedelta(days=count * days)
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for index in range(count):
        start = start_time + pd.Timedelta(days=index * days)
        end = start + pd.Timedelta(days=days)
        windows.append((start, end))
    return windows


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
    lines = [
        '# Strategy Validation',
        '',
        f'- Symbol: `{symbol}`',
        f'- Timeframe: `{timeframe}`',
        f'- Annual window: `{days}` days',
        f'- Rolling windows: `{WINDOW_COUNT}` non-overlapping `{WINDOW_DAYS}`-day windows',
        '',
        (
            '未通过验证的模式保持不可用于未来自动化 testnet 执行；'
            '只有状态为 `通过` 的模式可进入后续自动化模拟盘流程。'
        ),
        '',
        '| Mode | Margin | Status | Avg 30d Return % | Worst 30d Return % | Annual Return % | Max Drawdown % | Profit Factor | Annual Trades | Reasons |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        reasons = '；'.join(row.reasons) if row.reasons else '全部阈值通过'
        lines.append(
            '| '
            f'{row.mode.value} | '
            f'{row.margin_mode.value} | '
            f'{row.status} | '
            f'{row.avg_window_return_pct:.2f} | '
            f'{row.worst_window_return_pct:.2f} | '
            f'{row.annual_return_pct:.2f} | '
            f'{row.max_drawdown_pct:.2f} | '
            f'{row.profit_factor:.2f} | '
            f'{row.annual_trades} | '
            f'{reasons} |'
        )
    lines.append('')
    return '\n'.join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Validate stable signal strategy modes.')
    parser.add_argument('--symbol', default='ETH/USDT')
    parser.add_argument('--days', type=int, default=365)
    parser.add_argument('--output', type=Path, required=True)
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
    )
    passed = sum(1 for row in rows if row.status == '通过')
    logger.info('validation rows=%s passed=%s output=%s', len(rows), passed, args.output)


if __name__ == '__main__':
    main()
