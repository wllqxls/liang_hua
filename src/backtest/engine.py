"""
回测引擎模块：封装 backtesting.py，提供统一的运行和结果提取接口。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import ccxt
import pandas as pd
from backtesting import Strategy
from backtesting.lib import FractionalBacktest

from src.data.fetcher import DataFetcher, _COLUMNS
from src.strategies.risk import estimate_liquidation_price

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
    total_funding_fee: float = 0.0
    result_path: str | None = None

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
        leverage: float = 1.0,
        slippage_rate: float = 0.0,
        funding_rate: float = 0.0,
        maintenance_margin_rate: float = 0.005,
        save_result: bool = False,
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
            spread=slippage_rate,
            commission=commission,
            margin=1 / max(leverage, 1),
            hedging=False,
            finalize_trades=True,
        )

        logger.info(
            "Running backtest: %s %s %s (cash=%.0f)",
            strategy_class.__name__, symbol, timeframe, cash,
        )

        strategy_kwargs.setdefault("leverage", leverage)
        strategy_kwargs.setdefault("maintenance_margin_rate", maintenance_margin_rate)
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
        total_funding_fee = 0.0
        if hasattr(stats, "_trades") and stats._trades is not None:
            trades_df = stats._trades
            if hasattr(trades_df, "iterrows"):
                for _, t in trades_df.iterrows():
                    size = float(t.get("Size", 0))
                    entry_price = float(t.get("EntryPrice", 0))
                    exit_price = float(t.get("ExitPrice", 0))
                    side = "short" if size < 0 else "long"
                    notional = abs(size) * entry_price
                    margin_amount = notional / max(leverage, 1)
                    entry_time = str(t.get("EntryTime", ""))
                    exit_time = str(t.get("ExitTime", ""))
                    funding_fee = _estimate_funding_fee(entry_time, exit_time, notional, funding_rate)
                    total_funding_fee += funding_fee
                    trade_list.append({
                        "entry_time": entry_time,
                        "exit_time": exit_time,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "side": side,
                        "size": size,
                        "margin_amount": margin_amount,
                        "notional_amount": notional,
                        "leverage": leverage,
                        "liquidation_price": estimate_liquidation_price(
                            side=side,
                            entry_price=entry_price,
                            leverage=leverage,
                            maintenance_margin_rate=maintenance_margin_rate,
                        ),
                        "funding_fee": funding_fee,
                        "pnl": float(t.get("PnL", 0)) - funding_fee,
                        "pnl_pct": float(t.get("ReturnPct", 0)) * 100,
                        "exit_reason": _infer_exit_reason(side, exit_price, t.get("TP"), t.get("SL")),
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
            total_funding_fee=total_funding_fee,
        )
        if save_result:
            result.result_path = self.save_result(result, symbol=symbol, timeframe=timeframe, strategy=strategy_class.__name__)

        logger.info("Backtest result: %s", result.summary())
        return result

    def save_result(self, result: BacktestResult, symbol: str, timeframe: str, strategy: str) -> str:
        """保存回测记录到 results/ 目录。"""
        results_dir = Path("./results")
        results_dir.mkdir(parents=True, exist_ok=True)
        safe_symbol = symbol.replace("/", "_")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = results_dir / f"{stamp}_{safe_symbol}_{timeframe}_{strategy}.json"
        path.write_text(
            json.dumps(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "strategy": strategy,
                    "summary": {
                        "total_return_pct": result.total_return_pct,
                        "win_rate_pct": result.win_rate_pct,
                        "max_drawdown_pct": result.max_drawdown_pct,
                        "sharpe_ratio": result.sharpe_ratio,
                        "num_trades": result.num_trades,
                        "total_funding_fee": result.total_funding_fee,
                    },
                    "equity_curve": result.equity_curve,
                    "trade_list": result.trade_list,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return str(path)


def _estimate_funding_fee(entry_time: str, exit_time: str, notional: float, funding_rate: float) -> float:
    if funding_rate <= 0 or notional <= 0:
        return 0.0
    try:
        entry = pd.to_datetime(entry_time)
        exit_ = pd.to_datetime(exit_time)
    except (TypeError, ValueError):
        return 0.0
    hours = max((exit_ - entry).total_seconds() / 3600, 0)
    periods = hours / 8
    return notional * funding_rate * periods


def _infer_exit_reason(side: str, exit_price: float, take_profit: Any, stop_loss: Any) -> str:
    try:
        tp = float(take_profit)
        sl = float(stop_loss)
    except (TypeError, ValueError):
        return "策略平仓"
    if pd.notna(tp) and ((side == "long" and exit_price >= tp) or (side == "short" and exit_price <= tp)):
        return "止盈"
    if pd.notna(sl) and ((side == "long" and exit_price <= sl) or (side == "short" and exit_price >= sl)):
        return "止损/强平保护"
    return "策略平仓"
