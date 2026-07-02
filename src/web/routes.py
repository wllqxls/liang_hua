"""
FastAPI 路由：回测 API 和页面渲染。
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import ccxt
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.backtest.engine import BacktestEngine
from src.backtest.optimizer import (
    STAGE_ONE_BUDGET,
    STAGE_TWO_BUDGET,
    VALIDATION_BUDGET,
    SearchCandidate,
    available_entry_timeframes,
    build_stage_one_candidates,
    build_stage_two_candidates,
)
from src.data.fetcher import DataFetcher
from src.strategies.signal_models import SignalMode
from src.web.schemas import (
    BacktestRequest,
    BacktestResponse,
    DataFetchRequest,
    DataFetchResponse,
    DataStatus,
    EquityPoint,
    OptimizationCandidate,
    OptimizationJobCreated,
    OptimizationJobStatus,
    OptimizationResponse,
    TradeItem,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_templates_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

MODE_OPTIONS = [
    {
        'value': 'KEY_LEVEL',
        'label': '关键位',
        'description': '支撑假跌破做多，阻力假突破做空',
    },
    {
        'value': 'RSI_REVERSAL',
        'label': 'RSI 反转',
        'description': 'RSI 极值配合布林带收回',
    },
    {
        'value': 'KEY_LEVEL_RSI',
        'label': '关键位 + RSI 反转',
        'description': '关键位优先，RSI 仅作兜底',
    },
]
MODE_LABELS = {option['value']: option['label'] for option in MODE_OPTIONS}

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
]

MIN_QUALITY_TRADES = 5
MAX_ALLOWED_DRAWDOWN_PCT = -30.0
MIN_ALLOWED_WIN_RATE_PCT = 28.0
MIN_ALLOWED_PROFIT_FACTOR = 1.05
VALIDATION_POOL_SIZE = 10
RANDOM_VALIDATION_WINDOWS = 2
SEARCH_SOFT_LIMIT_SECONDS = 480.0
SEARCH_HARD_LIMIT_SECONDS = 600.0
SEARCH_TOTAL_BUDGET = STAGE_ONE_BUDGET + STAGE_TWO_BUDGET + VALIDATION_BUDGET
MAX_STORED_OPTIMIZATION_JOBS = 20

_optimization_jobs: OrderedDict[str, dict] = OrderedDict()
_optimization_jobs_lock = threading.Lock()


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


@dataclass
class ValidationReport:
    """样本外和随机窗口验证结果。"""

    out_sample_return_pct: float
    out_sample_quality_score: float
    random_pass_rate_pct: float
    random_avg_return_pct: float
    random_worst_return_pct: float
    robustness_score: float
    robustness_label: str


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """回测主页面。"""
    context = {
        "request": request,
        "symbols": SYMBOLS,
        "timeframes": TIMEFRAMES,
        "modes": MODE_OPTIONS,
    }
    return templates.TemplateResponse(request, "backtest.html", context)


@router.post("/api/backtest", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest) -> BacktestResponse:
    """运行回测。"""
    if req.opening_amount > req.cash:
        raise HTTPException(status_code=422, detail='开仓金额不能大于账户总金额')
    entry_fee = req.opening_amount * req.leverage * req.taker_fee
    if req.opening_amount + entry_fee > req.cash:
        raise HTTPException(status_code=422, detail='账户余额必须覆盖开仓金额和开仓手续费')

    try:
        engine = BacktestEngine(data_dir="./data")
        result = engine.run_signal_mode(
            symbol=req.symbol,
            timeframe=req.timeframe,
            mode=req.mode,
            backtest_days=req.backtest_days,
            cash=req.cash,
            opening_amount=req.opening_amount,
            margin_mode=req.margin_mode,
            leverage=req.leverage,
            maker_fee=req.maker_fee,
            taker_fee=req.taker_fee,
            slippage_rate=req.slippage_rate,
            funding_rate=req.funding_rate,
            maintenance_margin_rate=req.maintenance_margin_rate,
            save_result=True,
        )
        quality = _assess_backtest_quality(
            result=result,
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
        _log_safe_backtest_error('backtest_data_missing', e)
        raise HTTPException(
            status_code=404,
            detail=(
                f'缺少回测所需数据文件（入场周期 {req.timeframe}、1h、4h），'
                '请先补齐数据'
            ),
        ) from None
    except ValueError as e:
        _log_safe_backtest_error('backtest_invalid_input', e)
        raise HTTPException(status_code=422, detail='回测参数或数据格式无效') from None
    except Exception as e:
        _log_safe_backtest_error('backtest_internal_error', e)
        raise HTTPException(status_code=500, detail='回测服务内部错误，请稍后重试') from None


def _log_safe_backtest_error(event: str, error: Exception) -> None:
    """Log an error category without exception messages or tracebacks."""
    logger.error('event=%s exception_type=%s', event, type(error).__name__)


@router.post('/api/optimize/jobs', response_model=OptimizationJobCreated)
async def create_optimization_job(req: BacktestRequest) -> OptimizationJobCreated:
    """Start one progressive optimization job in a background thread."""
    if req.opening_amount > req.cash:
        return OptimizationJobCreated(success=False, error='开仓金额不能大于初始资金')
    timeframes = available_entry_timeframes(Path('./data'), req.symbol)
    if not timeframes:
        return OptimizationJobCreated(
            success=False,
            error='没有可用入场周期，请补齐同一币种的 5m/15m 入场数据及 1h、4h 数据',
        )

    with _optimization_jobs_lock:
        if any(job['state'] in {'queued', 'running'} for job in _optimization_jobs.values()):
            return OptimizationJobCreated(success=False, error='已有搜索任务正在运行，请等待完成')
        job_id = uuid.uuid4().hex
        _optimization_jobs[job_id] = _new_optimization_job(job_id)
        while len(_optimization_jobs) > MAX_STORED_OPTIMIZATION_JOBS:
            _optimization_jobs.popitem(last=False)

    worker = threading.Thread(
        target=_run_optimization_job,
        args=(job_id, req),
        daemon=True,
        name=f'optimization-{job_id[:8]}',
    )
    worker.start()
    return OptimizationJobCreated(success=True, job_id=job_id)


@router.get('/api/optimize/jobs/{job_id}', response_model=OptimizationJobStatus)
async def get_optimization_job(job_id: str) -> OptimizationJobStatus:
    """Return a snapshot of one progressive optimization job."""
    with _optimization_jobs_lock:
        job = _optimization_jobs.get(job_id)
        if job is None:
            return OptimizationJobStatus(success=False, job_id=job_id, state='missing', error='搜索任务不存在')
        snapshot = dict(job)
    return OptimizationJobStatus(**snapshot)


@router.post("/api/optimize", response_model=OptimizationResponse)
async def optimize_backtest(req: BacktestRequest) -> OptimizationResponse:
    """Run the same deterministic pipeline synchronously."""
    if req.opening_amount > req.cash:
        return OptimizationResponse(success=False, candidates=[], error='开仓金额不能大于初始资金')
    return _progressive_optimize(req, lambda **_: None)


def _new_optimization_job(job_id: str) -> dict:
    now = time.monotonic()
    return {
        'success': True,
        'job_id': job_id,
        'state': 'queued',
        'stage': '等待',
        'evaluated_count': 0,
        'total_budget': SEARCH_TOTAL_BUDGET,
        'filtered_count': 0,
        'elapsed_seconds': 0.0,
        'estimated_remaining_seconds': 0.0,
        'partial': False,
        'candidates': [],
        'error': None,
        '_started_at': now,
    }


def _reset_optimization_jobs_for_tests() -> None:
    """Clear process-local jobs between tests."""
    with _optimization_jobs_lock:
        _optimization_jobs.clear()


def _update_optimization_job(job_id: str, **values: object) -> None:
    with _optimization_jobs_lock:
        job = _optimization_jobs.get(job_id)
        if job is None:
            return
        job.update(values)
        started_at = float(job['_started_at'])
        elapsed = max(0.0, time.monotonic() - started_at)
        job['elapsed_seconds'] = round(elapsed, 1)
        evaluated = int(job.get('evaluated_count', 0))
        total = int(job.get('total_budget', SEARCH_TOTAL_BUDGET))
        if evaluated > 0:
            job['estimated_remaining_seconds'] = round(max(0.0, elapsed / evaluated * (total - evaluated)), 1)


def _run_optimization_job(job_id: str, req: BacktestRequest) -> None:
    _update_optimization_job(job_id, state='running', stage='粗筛')

    def progress(**values: object) -> None:
        _update_optimization_job(job_id, **values)

    try:
        response = _progressive_optimize(req, progress)
        _update_optimization_job(
            job_id,
            state='completed' if response.success else 'failed',
            stage='完成' if response.success else '失败',
            evaluated_count=response.evaluated_count,
            filtered_count=response.filtered_count,
            partial=response.partial,
            candidates=[candidate.model_dump() for candidate in response.candidates],
            error=response.error,
        )
    except Exception as exc:
        logger.exception('渐进式参数搜索失败')
        _update_optimization_job(job_id, state='failed', stage='失败', error=str(exc))


def _progressive_optimize(
    req: BacktestRequest,
    progress: Callable[..., None],
) -> OptimizationResponse:
    """Run deterministic coarse, local, and robustness search stages."""
    started_at = time.monotonic()
    entry_timeframes = available_entry_timeframes(Path('./data'), req.symbol)
    if not entry_timeframes:
        return OptimizationResponse(success=False, candidates=[], error='没有可用入场周期')
    seed_key = '|'.join([
        req.symbol,
        req.margin_mode.value,
        str(req.taker_fee),
        str(req.slippage_rate),
        str(req.funding_rate),
    ])
    stage_one = build_stage_one_candidates(
        entry_timeframes=entry_timeframes,
        modes=list(SignalMode),
        margin_mode=req.margin_mode,
        current_leverage=req.leverage,
        seed_key=seed_key,
    )
    total_budget = len(stage_one) + STAGE_TWO_BUDGET + VALIDATION_BUDGET
    engine = BacktestEngine(data_dir='./data')
    bounds_cache: dict[str, tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp, int]] = {}
    rankless: list[dict] = []
    evaluated_count = 0
    filtered_count = 0
    partial = False

    for candidate in stage_one:
        if _candidate_budget_exhausted(started_at, evaluated_count):
            partial = True
            break
        item, filtered = _evaluate_progressive_candidate(engine, req, candidate, bounds_cache)
        evaluated_count += 1
        filtered_count += int(filtered)
        if item is not None:
            rankless.append(item)
        progress(
            stage='粗筛',
            evaluated_count=evaluated_count,
            total_budget=total_budget,
            filtered_count=filtered_count,
            partial=partial,
        )

    stage_one_best = sorted(rankless, key=lambda item: item['score'], reverse=True)[:12]
    stage_two_bases = [_search_candidate_from_item(item) for item in stage_one_best]
    stage_two = build_stage_two_candidates(
        stage_two_bases,
        seed_key=seed_key,
    )
    total_budget = len(stage_one) + len(stage_two) + VALIDATION_BUDGET
    for candidate in stage_two:
        if _candidate_budget_exhausted(started_at, evaluated_count):
            partial = True
            break
        item, filtered = _evaluate_progressive_candidate(engine, req, candidate, bounds_cache)
        evaluated_count += 1
        filtered_count += int(filtered)
        if item is not None:
            rankless.append(item)
        progress(
            stage='精搜',
            evaluated_count=evaluated_count,
            total_budget=total_budget,
            filtered_count=filtered_count,
            partial=partial,
        )

    validation_pool = sorted(rankless, key=lambda item: item['score'], reverse=True)[:VALIDATION_POOL_SIZE]
    validated_pool: list[dict] = []
    for item in validation_pool:
        if time.monotonic() - started_at >= SEARCH_HARD_LIMIT_SECONDS:
            partial = True
            break
        data_start, data_end = _load_data_bounds(engine, req.symbol, item['timeframe'])
        _, _, out_start, out_end = _split_validation_bounds(data_start, data_end, req.backtest_days)
        out_sample_days = max(1, math.ceil((out_end - out_start).total_seconds() / 86400))
        validation = _validate_candidate(
            engine=engine,
            req=req,
            item=item,
            out_start=out_start,
            out_end=out_end,
            out_sample_days=out_sample_days,
            data_start=data_start,
            data_end=data_end,
        )
        item.update({
            'out_sample_return_pct': validation.out_sample_return_pct,
            'out_sample_quality_score': validation.out_sample_quality_score,
            'random_pass_rate_pct': validation.random_pass_rate_pct,
            'random_avg_return_pct': validation.random_avg_return_pct,
            'random_worst_return_pct': validation.random_worst_return_pct,
            'robustness_score': validation.robustness_score,
            'robustness_label': validation.robustness_label,
        })
        item['score'] += validation.robustness_score * 0.8
        validated_pool.append(item)
        evaluated_count += 1 + RANDOM_VALIDATION_WINDOWS
        progress(
            stage='稳健验证',
            evaluated_count=evaluated_count,
            total_budget=total_budget,
            filtered_count=filtered_count,
            partial=partial,
        )

    ranked = sorted(validated_pool, key=lambda item: item['score'], reverse=True)[:10]
    for item in ranked[:3]:
        if time.monotonic() - started_at >= SEARCH_HARD_LIMIT_SECONDS:
            partial = True
            break
        long_return, long_days, calls = _long_window_validation(engine, req, item)
        item['long_window_return_pct'] = long_return
        item['long_window_days'] = long_days
        evaluated_count += calls
        progress(
            stage='长窗口验证',
            evaluated_count=evaluated_count,
            total_budget=total_budget,
            filtered_count=filtered_count,
            partial=partial,
        )

    candidates = [
        OptimizationCandidate(rank=index, **item)
        for index, item in enumerate(ranked, start=1)
    ]
    return OptimizationResponse(
        success=True,
        candidates=candidates,
        evaluated_count=evaluated_count,
        filtered_count=filtered_count,
        partial=partial,
    )


def _candidate_budget_exhausted(
    started_at: float,
    evaluated_count: int,
    *,
    now: float | None = None,
) -> bool:
    """Stop candidate generation early enough to reserve validation time."""
    elapsed = max(0.0, (time.monotonic() if now is None else now) - started_at)
    if elapsed >= SEARCH_SOFT_LIMIT_SECONDS:
        return True
    if evaluated_count < 3:
        return False
    average_seconds = elapsed / evaluated_count
    return elapsed + average_seconds * VALIDATION_BUDGET >= SEARCH_HARD_LIMIT_SECONDS


def _evaluate_progressive_candidate(
    engine: BacktestEngine,
    req: BacktestRequest,
    candidate: SearchCandidate,
    bounds_cache: dict[str, tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp, int]],
) -> tuple[dict | None, bool]:
    if candidate.timeframe not in bounds_cache:
        data_start, data_end = _load_data_bounds(engine, req.symbol, candidate.timeframe)
        in_start, in_end, _, _ = _split_validation_bounds(data_start, data_end, req.backtest_days)
        in_days = max(1, math.ceil((in_end - in_start).total_seconds() / 86400))
        bounds_cache[candidate.timeframe] = (data_start, data_end, in_start, in_end, in_days)
    _, _, in_start, in_end, in_days = bounds_cache[candidate.timeframe]
    try:
        result = engine.run_signal_mode(
            symbol=req.symbol,
            timeframe=candidate.timeframe,
            mode=candidate.mode,
            window_start=in_start,
            window_end=in_end,
            cash=req.cash,
            opening_amount=req.opening_amount,
            margin_mode=candidate.margin_mode,
            leverage=candidate.leverage,
            maker_fee=req.maker_fee,
            taker_fee=req.taker_fee,
            slippage_rate=req.slippage_rate,
            funding_rate=req.funding_rate,
            maintenance_margin_rate=req.maintenance_margin_rate,
        )
    except Exception:
        logger.exception('渐进搜索候选失败')
        return None, False
    quality = _assess_backtest_quality(
        result=result,
        backtest_days=in_days,
    )
    if not quality.passes_filter:
        return None, True
    total_return_pct = _finite_number(result.total_return_pct)
    max_drawdown_pct = _finite_number(result.max_drawdown_pct)
    win_rate_pct = _finite_number(result.win_rate_pct)
    score = _optimization_score(
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        win_rate_pct=win_rate_pct,
        num_trades=result.num_trades,
        quality_score=quality.score,
        profit_factor=quality.profit_factor,
        max_consecutive_losses=quality.max_consecutive_losses,
    )
    return {
        'mode': candidate.mode,
        'mode_label': MODE_LABELS[candidate.mode.value],
        'timeframe': candidate.timeframe,
        'margin_mode': candidate.margin_mode,
        'leverage': candidate.leverage,
        'total_return_pct': total_return_pct,
        'max_drawdown_pct': max_drawdown_pct,
        'win_rate_pct': win_rate_pct,
        'out_sample_return_pct': 0.0,
        'out_sample_quality_score': 0.0,
        'random_pass_rate_pct': 0.0,
        'random_avg_return_pct': 0.0,
        'random_worst_return_pct': 0.0,
        'long_window_return_pct': 0.0,
        'long_window_days': 0,
        'robustness_score': 0.0,
        'robustness_label': '未验证',
        'num_trades': result.num_trades,
        'quality_score': quality.score,
        'quality_grade': quality.grade,
        'quality_label': quality.label,
        'quality_reasons': quality.reasons,
        'profit_factor': quality.profit_factor,
        'avg_win_loss_ratio': quality.avg_win_loss_ratio,
        'max_consecutive_losses': quality.max_consecutive_losses,
        'score': score,
    }, False


def _search_candidate_from_item(item: dict) -> SearchCandidate:
    return SearchCandidate(
        mode=item['mode'],
        timeframe=item['timeframe'],
        leverage=item['leverage'],
        margin_mode=item['margin_mode'],
    )


def _long_window_validation(
    engine: BacktestEngine,
    req: BacktestRequest,
    item: dict,
) -> tuple[float, int, int]:
    data_start, data_end = _load_data_bounds(engine, req.symbol, item['timeframe'])
    returns: list[float] = []
    longest = 0
    for days in [90, 180]:
        start = max(data_start, data_end - pd.Timedelta(days=days))
        actual_days = max(1, math.ceil((data_end - start).total_seconds() / 86400))
        result = _run_candidate_window(engine, req, item, start, data_end)
        returns.append(_finite_number(result.total_return_pct))
        longest = max(longest, actual_days)
        if start == data_start:
            break
    return (min(returns) if returns else 0.0), longest, len(returns)


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


def _load_data_bounds(engine: BacktestEngine, symbol: str, timeframe: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    safe_symbol = symbol.replace("/", "_")
    filepath = Path("./data") / f"{safe_symbol}_{timeframe}.csv"
    df = engine.load_data(filepath)
    if df.empty:
        raise ValueError("本地数据为空，无法做稳健性验证")
    return pd.Timestamp(df.index.min()), pd.Timestamp(df.index.max())


def _split_validation_bounds(
    data_start: pd.Timestamp,
    data_end: pd.Timestamp,
    backtest_days: int,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    end = data_end
    requested_start = end - pd.Timedelta(days=backtest_days)
    start = max(data_start, requested_start)
    duration = end - start
    if duration <= pd.Timedelta(hours=2):
        return start, end, start, end
    split = start + duration * 0.7
    return start, split, split, end


def _validate_candidate(
    engine: BacktestEngine,
    req: BacktestRequest,
    item: dict,
    out_start: pd.Timestamp,
    out_end: pd.Timestamp,
    out_sample_days: int,
    data_start: pd.Timestamp,
    data_end: pd.Timestamp,
) -> ValidationReport:
    try:
        out_result = _run_candidate_window(engine, req, item, out_start, out_end)
        out_quality = _assess_backtest_quality(
            result=out_result,
            backtest_days=out_sample_days,
        )
        out_return = _finite_number(out_result.total_return_pct)
        out_quality_score = out_quality.score
    except Exception:
        logger.exception("样本外验证失败")
        out_return = 0.0
        out_quality_score = 0.0

    random_returns: list[float] = []
    random_passes = 0
    validation_days = req.backtest_days
    windows = _random_validation_windows(data_start, data_end, validation_days, item)
    for start, end in windows:
        try:
            random_result = _run_candidate_window(engine, req, item, start, end)
            random_quality = _assess_backtest_quality(
                result=random_result,
                backtest_days=validation_days,
            )
        except Exception:
            logger.exception("随机窗口验证失败")
            continue
        random_return = _finite_number(random_result.total_return_pct)
        random_returns.append(random_return)
        if random_return > 0 and random_quality.passes_filter:
            random_passes += 1

    random_avg_return = sum(random_returns) / len(random_returns) if random_returns else 0.0
    random_worst_return = min(random_returns) if random_returns else 0.0
    random_pass_rate = (random_passes / len(windows) * 100) if windows else 0.0
    robustness_score = _robustness_score(
        out_return=out_return,
        out_quality_score=out_quality_score,
        random_pass_rate=random_pass_rate,
        random_avg_return=random_avg_return,
        random_worst_return=random_worst_return,
    )
    if robustness_score >= 70:
        robustness_label = "稳健"
    elif robustness_score >= 45:
        robustness_label = "观察"
    else:
        robustness_label = "不稳"
    return ValidationReport(
        out_sample_return_pct=round(out_return, 2),
        out_sample_quality_score=round(out_quality_score, 2),
        random_pass_rate_pct=round(random_pass_rate, 2),
        random_avg_return_pct=round(random_avg_return, 2),
        random_worst_return_pct=round(random_worst_return, 2),
        robustness_score=round(robustness_score, 2),
        robustness_label=robustness_label,
    )


def _run_candidate_window(
    engine: BacktestEngine,
    req: BacktestRequest,
    item: dict,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> object:
    return engine.run_signal_mode(
        symbol=req.symbol,
        timeframe=item.get('timeframe', req.timeframe),
        mode=item['mode'],
        window_start=start,
        window_end=end,
        cash=req.cash,
        opening_amount=req.opening_amount,
        margin_mode=item['margin_mode'],
        leverage=item["leverage"],
        maker_fee=req.maker_fee,
        taker_fee=req.taker_fee,
        slippage_rate=req.slippage_rate,
        funding_rate=req.funding_rate,
        maintenance_margin_rate=req.maintenance_margin_rate,
    )


def _random_validation_windows(
    data_start: pd.Timestamp,
    data_end: pd.Timestamp,
    days: int,
    item: dict,
    count: int = RANDOM_VALIDATION_WINDOWS,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    window = pd.Timedelta(days=days)
    if data_end - data_start <= window:
        return [(max(data_start, data_end - window), data_end)]
    seed_text = "|".join(
        str(item[key])
        for key in ['mode', 'timeframe', 'margin_mode', 'leverage']
    )
    seed = int(sha256(seed_text.encode("utf-8")).hexdigest()[:12], 16)
    rng = random.Random(seed)
    max_offset_seconds = int((data_end - data_start - window).total_seconds())
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    seen_offsets: set[int] = set()
    for _ in range(count * 3):
        if len(windows) >= count:
            break
        offset = rng.randint(0, max_offset_seconds)
        if offset in seen_offsets:
            continue
        seen_offsets.add(offset)
        start = data_start + pd.Timedelta(seconds=offset)
        windows.append((start, start + window))
    return windows or [(data_end - window, data_end)]


def _robustness_score(
    out_return: float,
    out_quality_score: float,
    random_pass_rate: float,
    random_avg_return: float,
    random_worst_return: float,
) -> float:
    score = 0.0
    score += out_quality_score * 0.45
    score += random_pass_rate * 0.35
    score += max(min(random_avg_return, 40), -40) * 0.35
    score += max(min(random_worst_return, 20), -40) * 0.25
    if out_return <= 0:
        score -= 15
    if random_worst_return < -10:
        score -= 10
    return max(min(score, 100), 0)


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
) -> float:
    score = 50.0
    score += max(min(total_return_pct, 60), -30) * 0.35
    score += max(min(win_rate_pct - 35, 35), -25) * 0.45
    score += max(max_drawdown_pct, -60) * 0.55
    score += min(profit_factor, 3.0) * 8
    score += min(num_trades / max(min_trades, 1), 2.0) * 6
    score += max(min(sharpe_ratio, 3.0), -1.0) * 4
    score -= max_consecutive_losses * 2
    return max(min(score, 100), 0)
