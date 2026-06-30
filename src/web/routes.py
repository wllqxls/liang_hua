"""
FastAPI 路由：回测 API 和页面渲染。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.backtest.engine import BacktestEngine
from src.strategies.sr_breakout import SRBreakout
from src.web.schemas import BacktestRequest, BacktestResponse, DataStatus, EquityPoint, TradeItem

logger = logging.getLogger(__name__)

router = APIRouter()

_templates_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

STRATEGIES: dict[str, type] = {
    "SRBreakout": SRBreakout,
    "SupportResistanceBreakout": SRBreakout,
}

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
]


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """回测主页面。"""
    context = {
        "request": request,
        "symbols": SYMBOLS,
        "timeframes": TIMEFRAMES,
        "strategies": list(STRATEGIES.keys()),
    }
    return templates.TemplateResponse(request, "backtest.html", context)


@router.post("/api/backtest", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest) -> BacktestResponse:
    """运行回测。"""
    strategy_class = STRATEGIES.get(req.strategy)
    if strategy_class is None:
        return _error_response(f"未知策略: {req.strategy}")

    try:
        engine = BacktestEngine(data_dir="./data")
        result = engine.run(
            strategy_class=strategy_class,
            symbol=req.symbol,
            timeframe=req.timeframe,
            lookback=req.lookback,
            cash=req.cash,
            commission=req.commission,
        )

        return BacktestResponse(
            success=True,
            total_return_pct=result.total_return_pct,
            win_rate_pct=result.win_rate_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            sharpe_ratio=result.sharpe_ratio,
            num_trades=result.num_trades,
            equity_curve=[
                EquityPoint(timestamp=p["timestamp"], equity=p["equity"])
                for p in result.equity_curve
            ],
            trade_list=[TradeItem(**t) for t in result.trade_list],
        )

    except FileNotFoundError as e:
        return _error_response(f"数据文件不存在: {e}")
    except Exception as e:
        logger.exception("回测失败")
        return _error_response(str(e))


@router.get("/api/data-status")
async def data_status() -> list[DataStatus]:
    """检查本地数据文件。"""
    data_dir = Path("./data")
    results: list[DataStatus] = []

    import pandas as pd

    for symbol in SYMBOLS[:4]:
        for tf in ["1h", "4h", "1d"]:
            safe_sym = symbol.replace("/", "_")
            filepath = data_dir / f"{safe_sym}_{tf}.csv"
            exists = filepath.exists()
            rows = None
            size = None
            if exists:
                try:
                    df = pd.read_csv(filepath)
                    rows = len(df)
                    size = filepath.stat().st_size / 1024
                except Exception:
                    pass
            results.append(DataStatus(
                symbol=symbol, timeframe=tf, exists=exists,
                rows=rows, file_size_kb=round(size, 1) if size else None,
            ))
    return results


def _error_response(msg: str) -> BacktestResponse:
    return BacktestResponse(
        success=False, error=msg,
        total_return_pct=0, win_rate_pct=0, max_drawdown_pct=0,
        sharpe_ratio=None, num_trades=0, equity_curve=[], trade_list=[],
    )
