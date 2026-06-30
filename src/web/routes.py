"""
FastAPI 路由：回测 API 和页面渲染。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.backtest.engine import BacktestEngine
from src.data.fetcher import DataFetcher
from src.strategies.key_level_scoring import KeyLevelScoring
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
    "KeyLevelScoring": KeyLevelScoring,
    "SRBreakout": SRBreakout,
    "SupportResistanceBreakout": SRBreakout,
    "MovingAverageCross": MovingAverageCross,
    "RSIReversion": RSIReversion,
}

STRATEGY_OPTIONS = [
    {
        "value": "KeyLevelScoring",
        "label": "关键位评分",
        "description": "评分策略：支撑阻力只定位关键位，结合影线、成交量、趋势判断做多、做空或不交易。",
    },
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

MIN_QUALITY_TRADES = 5
MAX_ALLOWED_DRAWDOWN_PCT = -30.0
MIN_ALLOWED_WIN_RATE_PCT = 28.0
MIN_ALLOWED_PROFIT_FACTOR = 1.05


@dataclass
class QualityReport:
    """策略质量评估结果。"""

    score: float
    grade: str
    label: str
    reasons: list[str]
    profit_factor: float
    avg_win_loss_ratio: float
    max_consecutive_losses: int
    passes_filter: bool


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
            context_timeframe=req.context_timeframe,
            backtest_days=req.backtest_days,
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
        quality = _assess_backtest_quality(
            result=result,
            take_profit_amount=req.take_profit_amount,
            stop_loss_amount=req.stop_loss_amount,
            backtest_days=req.backtest_days,
        )

        return BacktestResponse(
            success=True,
            total_return_pct=result.total_return_pct,
            win_rate_pct=result.win_rate_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            sharpe_ratio=result.sharpe_ratio,
            num_trades=result.num_trades,
            total_funding_fee=result.total_funding_fee,
            quality_score=quality.score,
            quality_grade=quality.grade,
            quality_label=quality.label,
            quality_reasons=quality.reasons,
            profit_factor=quality.profit_factor,
            avg_win_loss_ratio=quality.avg_win_loss_ratio,
            max_consecutive_losses=quality.max_consecutive_losses,
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

    lookbacks = _nearby_ints(req.lookback, [1, 1.5], min_value=2, max_value=500)
    leverages = _nearby_leverages(req.leverage)
    take_profit_base = req.take_profit_amount if req.take_profit_amount > 0 else req.position_amount * 0.5
    take_profits = _nearby_numbers(
        take_profit_base,
        [1, 1.5],
        min_value=0.1,
        max_value=req.position_amount * req.leverage,
    )
    stop_losses = _nearby_numbers(req.stop_loss_amount, [0.75, 1], min_value=0.1, max_value=req.position_amount)

    engine = BacktestEngine(data_dir="./data")
    candidates: list[OptimizationCandidate] = []
    rankless: list[dict] = []
    evaluated_count = 0
    filtered_count = 0

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
                                context_timeframe=req.context_timeframe,
                                backtest_days=req.backtest_days,
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
                        evaluated_count += 1
                        total_return_pct = _finite_number(result.total_return_pct)
                        max_drawdown_pct = _finite_number(result.max_drawdown_pct)
                        win_rate_pct = _finite_number(result.win_rate_pct)
                        quality = _assess_backtest_quality(
                            result=result,
                            take_profit_amount=take_profit_amount,
                            stop_loss_amount=stop_loss_amount,
                            backtest_days=req.backtest_days,
                        )
                        if not quality.passes_filter:
                            filtered_count += 1
                            continue
                        score = _optimization_score(
                            total_return_pct=total_return_pct,
                            max_drawdown_pct=max_drawdown_pct,
                            win_rate_pct=win_rate_pct,
                            num_trades=result.num_trades,
                            quality_score=quality.score,
                            profit_factor=quality.profit_factor,
                            max_consecutive_losses=quality.max_consecutive_losses,
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
                            "quality_score": quality.score,
                            "quality_grade": quality.grade,
                            "quality_label": quality.label,
                            "quality_reasons": quality.reasons,
                            "profit_factor": quality.profit_factor,
                            "avg_win_loss_ratio": quality.avg_win_loss_ratio,
                            "max_consecutive_losses": quality.max_consecutive_losses,
                            "score": score,
                        })

    ranked = sorted(rankless, key=lambda item: item["score"], reverse=True)[:10]
    for index, item in enumerate(ranked, start=1):
        candidates.append(OptimizationCandidate(rank=index, **item))
    return OptimizationResponse(
        success=True,
        candidates=candidates,
        evaluated_count=evaluated_count,
        filtered_count=filtered_count,
    )


@router.get("/api/data-status")
async def data_status() -> list[DataStatus]:
    """检查本地数据文件。"""
    data_dir = Path("./data")
    results: list[DataStatus] = []

    for symbol in SYMBOLS[:4]:
        for tf in ["5m", "15m", "1h", "4h"]:
            results.append(_inspect_data_file(data_dir, symbol, tf))
    return results


@router.post("/api/fetch-data", response_model=DataFetchResponse)
async def fetch_data(req: DataFetchRequest) -> DataFetchResponse:
    """拉取历史 K 线数据并保存到本地 CSV。"""
    if req.symbol not in SYMBOLS:
        return _fetch_error_response(req, f"暂不支持的交易对象: {req.symbol}")
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
    quality_score: float,
    profit_factor: float,
    max_consecutive_losses: int,
) -> float:
    """给自动交易候选打稳定性分，避免低胜率单次暴利排太靠前。"""
    low_win_penalty = max(45 - win_rate_pct, 0) * 2
    few_trades_penalty = max(5 - num_trades, 0) * 2
    trade_bonus = min(num_trades, 30) * 0.1
    return (
        quality_score
        + total_return_pct * 0.4
        + max_drawdown_pct
        + win_rate_pct * 0.2
        + min(profit_factor, 3.0) * 3
        + trade_bonus
        - low_win_penalty
        - few_trades_penalty
        - max_consecutive_losses * 1.5
    )


def _assess_backtest_quality(
    result: object,
    take_profit_amount: float,
    stop_loss_amount: float,
    backtest_days: int,
) -> QualityReport:
    """给回测结果做实盘重复执行视角的质量评估。"""
    total_return_pct = _finite_number(getattr(result, "total_return_pct", 0.0))
    win_rate_pct = _finite_number(getattr(result, "win_rate_pct", 0.0))
    max_drawdown_pct = _finite_number(getattr(result, "max_drawdown_pct", 0.0))
    sharpe_ratio = _finite_number(getattr(result, "sharpe_ratio", 0.0))
    num_trades = int(getattr(result, "num_trades", 0) or 0)
    trade_list = list(getattr(result, "trade_list", []) or [])
    pnl_values = [_finite_number(trade.get("pnl")) for trade in trade_list if isinstance(trade, dict)]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = _profit_factor(gross_win, gross_loss)
    avg_win_loss_ratio = _avg_win_loss_ratio(wins, losses)
    max_consecutive_losses = _max_consecutive_losses(pnl_values)
    min_trades = _minimum_quality_trades(backtest_days)

    reasons: list[str] = []
    hard_reasons: list[str] = []

    if take_profit_amount <= 0 or stop_loss_amount <= 0:
        hard_reasons.append("必须同时设置止盈和止损")
    if num_trades < min_trades:
        hard_reasons.append(f"交易次数少于 {min_trades} 笔，样本不足")
    if total_return_pct <= 0:
        hard_reasons.append("扣除成本后总收益不为正")
    if max_drawdown_pct < MAX_ALLOWED_DRAWDOWN_PCT:
        hard_reasons.append("最大回撤超过 30%")
    if win_rate_pct < MIN_ALLOWED_WIN_RATE_PCT:
        hard_reasons.append("胜率过低，容易依赖少数大行情")
    if profit_factor < MIN_ALLOWED_PROFIT_FACTOR:
        hard_reasons.append("盈亏比不足，亏损单吞噬盈利单")

    if max_consecutive_losses >= 5:
        reasons.append("连续亏损偏多，实盘心理和资金压力较大")

    reasons = hard_reasons + reasons
    if not reasons:
        reasons.append("通过严格过滤")

    score = _quality_score(
        total_return_pct=total_return_pct,
        win_rate_pct=win_rate_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        num_trades=num_trades,
        min_trades=min_trades,
        profit_factor=profit_factor,
        max_consecutive_losses=max_consecutive_losses,
        has_take_profit_stop_loss=take_profit_amount > 0 and stop_loss_amount > 0,
    )
    passes_filter = len(hard_reasons) == 0
    if not passes_filter or score < 45:
        grade = "reject"
        label = "不建议"
    elif score < 70:
        grade = "watch"
        label = "谨慎"
    else:
        grade = "recommend"
        label = "推荐"

    return QualityReport(
        score=round(score, 2),
        grade=grade,
        label=label,
        reasons=reasons,
        profit_factor=round(profit_factor, 2),
        avg_win_loss_ratio=round(avg_win_loss_ratio, 2),
        max_consecutive_losses=max_consecutive_losses,
        passes_filter=passes_filter,
    )


def _minimum_quality_trades(backtest_days: int) -> int:
    return max(MIN_QUALITY_TRADES, min(30, math.ceil(backtest_days / 10)))


def _profit_factor(gross_win: float, gross_loss: float) -> float:
    if gross_win <= 0:
        return 0.0
    if gross_loss <= 0:
        return 99.0
    return gross_win / gross_loss


def _avg_win_loss_ratio(wins: list[float], losses: list[float]) -> float:
    if not wins:
        return 0.0
    if not losses:
        return 99.0
    return (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))


def _max_consecutive_losses(pnl_values: list[float]) -> int:
    max_losses = 0
    current_losses = 0
    for pnl in pnl_values:
        if pnl < 0:
            current_losses += 1
            max_losses = max(max_losses, current_losses)
        else:
            current_losses = 0
    return max_losses


def _quality_score(
    total_return_pct: float,
    win_rate_pct: float,
    max_drawdown_pct: float,
    sharpe_ratio: float,
    num_trades: int,
    min_trades: int,
    profit_factor: float,
    max_consecutive_losses: int,
    has_take_profit_stop_loss: bool,
) -> float:
    score = 50.0
    score += max(min(total_return_pct, 60), -30) * 0.35
    score += max(min(win_rate_pct - 35, 35), -25) * 0.45
    score += max(max_drawdown_pct, -60) * 0.55
    score += min(profit_factor, 3.0) * 8
    score += min(num_trades / max(min_trades, 1), 2.0) * 6
    score += max(min(sharpe_ratio, 3.0), -1.0) * 4
    score -= max_consecutive_losses * 2
    if not has_take_profit_stop_loss:
        score -= 20
    return max(min(score, 100), 0)
