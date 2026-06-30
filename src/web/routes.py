"""
FastAPI 路由：回测 API 和页面渲染。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.backtest.engine import BacktestEngine
from src.data.fetcher import DataFetcher
from src.strategies.ma_cross import MovingAverageCross
from src.strategies.rsi_reversion import RSIReversion
from src.strategies.sr_breakout import SRBreakout
from src.web.schemas import (
    BacktestRequest,
    BacktestResponse,
    DataFetchRequest,
    DataFetchResponse,
    DataStatus,
    EquityPoint,
    TradeItem,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_templates_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

STRATEGIES: dict[str, type] = {
    "SRBreakout": SRBreakout,
    "SupportResistanceBreakout": SRBreakout,
    "MovingAverageCross": MovingAverageCross,
    "RSIReversion": RSIReversion,
}

STRATEGY_OPTIONS = [
    {
        "value": "SRBreakout",
        "label": "支撑阻力突破",
        "description": "规则策略：价格突破近期高点买入，亏损触发止损。",
    },
    {
        "value": "MovingAverageCross",
        "label": "均线金叉死叉",
        "description": "规则策略：快线上穿慢线买入，快线下穿慢线平仓。",
    },
    {
        "value": "RSIReversion",
        "label": "RSI 超卖反弹",
        "description": "规则策略：RSI 低位买入，高位或止损时平仓。",
    },
]

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
        "strategies": STRATEGY_OPTIONS,
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

    for symbol in SYMBOLS[:4]:
        for tf in ["1h", "4h", "1d"]:
            results.append(_inspect_data_file(data_dir, symbol, tf))
    return results


@router.post("/api/fetch-data", response_model=DataFetchResponse)
async def fetch_data(req: DataFetchRequest) -> DataFetchResponse:
    """拉取历史 K 线数据并保存到本地 CSV。"""
    if req.symbol not in SYMBOLS:
        return _fetch_error_response(req, f"暂不支持的交易对: {req.symbol}")
    if req.timeframe not in TIMEFRAMES:
        return _fetch_error_response(req, f"暂不支持的 K 线周期: {req.timeframe}")

    data_dir = Path("./data")
    since = datetime.now(timezone.utc) - timedelta(days=req.days)

    try:
        DataFetcher().fetch_and_save(
            symbol=req.symbol,
            timeframe=req.timeframe,
            since=since,
            data_dir=str(data_dir),
        )
        status = _inspect_data_file(data_dir, req.symbol, req.timeframe)
        return DataFetchResponse(
            success=True,
            symbol=req.symbol,
            timeframe=req.timeframe,
            rows=status.rows,
            file_size_kb=status.file_size_kb,
        )
    except (ccxt.BaseError, OSError, ValueError) as e:
        logger.exception("数据拉取失败")
        return _fetch_error_response(
            req,
            f"数据拉取失败: {e}。请检查网络、代理或交易所接口状态。",
        )


def _inspect_data_file(data_dir: Path, symbol: str, timeframe: str) -> DataStatus:
    safe_sym = symbol.replace("/", "_")
    filepath = data_dir / f"{safe_sym}_{timeframe}.csv"
    exists = filepath.exists()
    rows = None
    size = None

    if exists:
        try:
            df = pd.read_csv(filepath)
            rows = len(df)
            size = filepath.stat().st_size / 1024
        except (OSError, pd.errors.ParserError):
            logger.warning("无法读取数据文件: %s", filepath)

    return DataStatus(
        symbol=symbol,
        timeframe=timeframe,
        exists=exists,
        rows=rows,
        file_size_kb=round(size, 1) if size else None,
    )


def _fetch_error_response(req: DataFetchRequest, msg: str) -> DataFetchResponse:
    return DataFetchResponse(
        success=False,
        symbol=req.symbol,
        timeframe=req.timeframe,
        rows=None,
        file_size_kb=None,
        error=msg,
    )


def _error_response(msg: str) -> BacktestResponse:
    return BacktestResponse(
        success=False, error=msg,
        total_return_pct=0, win_rate_pct=0, max_drawdown_pct=0,
        sharpe_ratio=None, num_trades=0, equity_curve=[], trade_list=[],
    )
