"""
回测引擎模块：封装 backtesting.py，提供统一的运行和结果提取接口。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ccxt
import pandas as pd
from backtesting import Strategy
from backtesting.lib import FractionalBacktest

from src.data.fetcher import DataFetcher, _COLUMNS

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """回测结果数据结构。"""

    total_return_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None
    num_trades: int
    equity_curve: list[dict[str, Any]]
    trade_list: list[dict[str, Any]]

    def summary(self) -> str:
        return (
            f"总收益: {self.total_return_pct:+.2f}%  "
            f"胜率: {self.win_rate_pct:.1f}%  "
            f"最大回撤: {self.max_drawdown_pct:.2f}%  "
            f"夏普: {self.sharpe_ratio or 'N/A'}  "
            f"交易次数: {self.num_trades}"
        )


class BacktestEngine:
    """回测引擎：加载数据 → 运行策略 → 输出结果。"""

    def __init__(self, data_dir: str | Path = "./data", fetcher: DataFetcher | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._fetcher = fetcher
        self._cache: dict[str, pd.DataFrame] = {}

    def load_data(self, filepath: Path | None = None) -> pd.DataFrame:
        """加载回测数据。"""
        if filepath is None:
            filepath = self._data_dir / "BTC_USDT_1h.csv"

        cache_key = str(filepath)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if filepath.exists():
            df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        else:
            stem = filepath.stem
            parts = stem.rsplit("_", 2)
            if len(parts) >= 3:
                symbol = f"{parts[0]}/{parts[1]}"
                timeframe = parts[2]
            else:
                symbol, timeframe = "BTC/USDT", "1h"

            logger.info("Data file not found, fetching %s %s...", symbol, timeframe)
            fetcher = self._fetcher or DataFetcher()
            try:
                df = fetcher.fetch_ohlcv(symbol=symbol, timeframe=timeframe)
            except (ccxt.BaseError, OSError, ValueError) as e:
                raise RuntimeError(
                    f"本地数据文件不存在: {filepath}。自动拉取 {symbol} {timeframe} 也失败，"
                    "请检查网络、代理或先手动运行数据拉取命令。"
                ) from e

            if df.empty:
                raise ValueError(f"没有获取到 {symbol} {timeframe} 的 K 线数据")

            filepath.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(filepath)

        missing_columns = [column for column in _COLUMNS if column not in df.columns]
        if missing_columns:
            raise ValueError(f"数据文件缺少必要列: {', '.join(missing_columns)}")

        df = df[_COLUMNS]
        self._cache[cache_key] = df
        return df

    def run(
        self,
        strategy_class: type[Strategy],
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        cash: float = 1_000_000,
        commission: float = 0.001,
        **strategy_kwargs: Any,
    ) -> BacktestResult:
        """运行回测。"""
        safe_symbol = symbol.replace("/", "_")
        filepath = self._data_dir / f"{safe_symbol}_{timeframe}.csv"
        df = self.load_data(filepath)

        bt = FractionalBacktest(
            df,
            strategy_class,
            cash=cash,
            commission=commission,
            hedging=False,
            finalize_trades=True,
        )

        logger.info(
            "Running backtest: %s %s %s (cash=%.0f)",
            strategy_class.__name__, symbol, timeframe, cash,
        )

        stats = bt.run(**strategy_kwargs)

        # 权益曲线
        equity_curve: list[dict] = []
        if hasattr(stats, "_equity_curve") and stats._equity_curve is not None:
            eq = stats._equity_curve
            if hasattr(eq, "columns") and "Equity" in eq.columns:
                equity_col = eq["Equity"]
            else:
                equity_col = eq.iloc[:, 0] if hasattr(eq, "iloc") else eq
            for i in range(len(equity_col)):
                ts = df.index[i] if i < len(df.index) else None
                ts_str = ts.isoformat() if ts is not None else None
                equity_curve.append({
                    "timestamp": ts_str,
                    "equity": float(equity_col.iloc[i]) if hasattr(equity_col, "iloc") else float(equity_col[i]),
                })

        # 交易记录
        trade_list: list[dict] = []
        if hasattr(stats, "_trades") and stats._trades is not None:
            trades_df = stats._trades
            if hasattr(trades_df, "iterrows"):
                for _, t in trades_df.iterrows():
                    trade_list.append({
                        "entry_time": str(t.get("EntryTime", "")),
                        "exit_time": str(t.get("ExitTime", "")),
                        "entry_price": float(t.get("EntryPrice", 0)),
                        "exit_price": float(t.get("ExitPrice", 0)),
                        "size": float(t.get("Size", 0)),
                        "pnl": float(t.get("PnL", 0)),
                        "pnl_pct": float(t.get("ReturnPct", 0)),
                    })

        # 夏普比率
        sharpe = None
        try:
            sr = getattr(stats, "Sharpe Ratio", None)
            if sr is not None and not pd.isna(sr):
                sharpe = float(sr)
        except Exception:
            pass

        result = BacktestResult(
            total_return_pct=float(stats["Return [%]"]),
            win_rate_pct=float(stats["Win Rate [%]"]),
            max_drawdown_pct=float(stats["Max. Drawdown [%]"]),
            sharpe_ratio=sharpe,
            num_trades=int(stats["# Trades"]),
            equity_curve=equity_curve,
            trade_list=trade_list,
        )

        logger.info("Backtest result: %s", result.summary())
        return result
