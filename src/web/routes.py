"""
FastAPI 路由：回测 API 和页面渲染。
"""

from __future__ import annotations

import logging
import math
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
    OptimizationCandidate,
    OptimizationResponse,
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
        "description": "规则策略：突破近期高点做多，跌破近期低点做空，方向由策略自动判断。",
    },
    {
        "value": "MovingAverageCross",
        "label": "均线金叉死叉",
        "description": "规则策略：快线上穿慢线做多，快线下穿慢线做空，方向由策略自动判断。",
    },
    {
        "value": "RSIReversion",
        "label": "RSI 超卖反弹",
        "description": "规则策略：RSI 低位做多，高位做空，方向由策略自动判断。",
    },
]

OPTIMIZATION_STRATEGIES = {
    option["value"]: {
        "class": STRATEGIES[option["value"]],
        "label": option["label"],
    }
    for option in STRATEGY_OPTIONS
}

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]

LEVERAGE_OPTIONS = [1, 2, 3, 5, 10, 20, 50, 100, 125, 150]

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
    if req.position_amount > req.cash:
        return _error_response("单笔逐仓金额不能大于初始资金")

    try:
        engine = BacktestEngine(data_dir="./data")
        result = engine.run(
            strategy_class=strategy_class,
            symbol=req.symbol,
            timeframe=req.timeframe,
            lookback=req.lookback,
            cash=req.cash,
            commission=req.taker_fee,
            leverage=req.leverage,
            slippage_rate=req.slippage_rate,
            funding_rate=req.funding_rate,
            maintenance_margin_rate=req.maintenance_margin_rate,
            save_result=True,
            position_amount=req.position_amount,
            take_profit_amount=req.take_profit_amount,
            stop_loss_amount=req.stop_loss_amount,
        )

        return BacktestResponse(
            success=True,
            total_return_pct=result.total_return_pct,
            win_rate_pct=result.win_rate_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            sharpe_ratio=result.sharpe_ratio,
            num_trades=result.num_trades,
            total_funding_fee=result.total_funding_fee,
            result_path=result.result_path,
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


@router.post("/api/optimize", response_model=OptimizationResponse)
async def optimize_backtest(req: BacktestRequest) -> OptimizationResponse:
    """基于当前参数，对多个策略和参数组合做一轮小型搜索。"""
    if req.strategy not in STRATEGIES:
        return OptimizationResponse(success=False, candidates=[], error=f"未知策略: {req.strategy}")
    if req.position_amount > req.cash:
        return OptimizationResponse(success=False, candidates=[], error="单笔逐仓金额不能大于初始资金")

    lookbacks = _nearby_ints(req.lookback, [0.5, 1, 2], min_value=2, max_value=500)
    leverages = _nearby_leverages(req.leverage)
    take_profit_base = req.take_profit_amount if req.take_profit_amount > 0 else req.position_amount * 0.5
    take_profits = _nearby_numbers(
        take_profit_base,
        [0.75, 1, 1.5],
        min_value=0.1,
        max_value=req.position_amount * req.leverage,
    )
    stop_losses = _nearby_numbers(req.stop_loss_amount, [0.5, 1, 1.5], min_value=0.1, max_value=req.position_amount)

    engine = BacktestEngine(data_dir="./data")
    candidates: list[OptimizationCandidate] = []
    rankless: list[dict] = []

    for strategy_name, strategy_info in OPTIMIZATION_STRATEGIES.items():
        for lookback in lookbacks:
            for leverage in leverages:
                for take_profit_amount in take_profits:
                    for stop_loss_amount in stop_losses:
                        try:
                            result = engine.run(
                                strategy_class=strategy_info["class"],
                                symbol=req.symbol,
                                timeframe=req.timeframe,
                                lookback=lookback,
                                cash=req.cash,
                                commission=req.taker_fee,
                                leverage=leverage,
                                slippage_rate=req.slippage_rate,
                                funding_rate=req.funding_rate,
                                maintenance_margin_rate=req.maintenance_margin_rate,
                                position_amount=req.position_amount,
                                take_profit_amount=take_profit_amount,
                                stop_loss_amount=stop_loss_amount,
                            )
                        except Exception:
                            logger.exception("参数搜索候选失败")
                            continue
                        total_return_pct = _finite_number(result.total_return_pct)
                        max_drawdown_pct = _finite_number(result.max_drawdown_pct)
                        win_rate_pct = _finite_number(result.win_rate_pct)
                        score = _optimization_score(
                            total_return_pct=total_return_pct,
                            max_drawdown_pct=max_drawdown_pct,
                            win_rate_pct=win_rate_pct,
                            num_trades=result.num_trades,
                        )
                        rankless.append({
                            "strategy": strategy_name,
                            "strategy_label": strategy_info["label"],
                            "lookback": lookback,
                            "leverage": leverage,
                            "take_profit_amount": take_profit_amount,
                            "stop_loss_amount": stop_loss_amount,
                            "total_return_pct": total_return_pct,
                            "max_drawdown_pct": max_drawdown_pct,
                            "win_rate_pct": win_rate_pct,
                            "num_trades": result.num_trades,
                            "score": score,
                        })

    ranked = sorted(rankless, key=lambda item: item["score"], reverse=True)[:10]
    for index, item in enumerate(ranked, start=1):
        candidates.append(OptimizationCandidate(rank=index, **item))
    return OptimizationResponse(success=True, candidates=candidates)


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


def _nearby_ints(value: int, factors: list[float], min_value: int, max_value: int) -> list[int]:
    values = {min(max(int(round(value * factor)), min_value), max_value) for factor in factors}
    return sorted(values)


def _nearby_numbers(value: float, factors: list[float], min_value: float, max_value: float) -> list[float]:
    values = {round(min(max(value * factor, min_value), max_value), 4) for factor in factors}
    return sorted(values)


def _nearby_leverages(value: float) -> list[float]:
    targets = [min(max(value * factor, 1), 150) for factor in [0.5, 1, 2]]
    selected = {
        min(LEVERAGE_OPTIONS, key=lambda option: abs(option - target))
        for target in targets
    }
    return [float(item) for item in sorted(selected)]


def _finite_number(value: float | None) -> float:
    if value is None or not math.isfinite(value):
        return 0.0
    return float(value)


def _optimization_score(
    total_return_pct: float,
    max_drawdown_pct: float,
    win_rate_pct: float,
    num_trades: int,
) -> float:
    """给自动交易候选打稳定性分，避免低胜率单次暴利排太靠前。"""
    low_win_penalty = max(45 - win_rate_pct, 0) * 2
    few_trades_penalty = max(5 - num_trades, 0) * 2
    trade_bonus = min(num_trades, 30) * 0.1
    return (
        total_return_pct
        + max_drawdown_pct
        + win_rate_pct * 0.2
        + trade_bonus
        - low_win_penalty
        - few_trades_penalty
    )
