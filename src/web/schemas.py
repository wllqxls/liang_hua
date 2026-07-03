"""
Pydantic 数据模型：API 请求/响应结构。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.strategies.signal_models import MarginMode, SignalMode


class BacktestRequest(BaseModel):
    """回测请求参数。"""

    model_config = ConfigDict(extra='forbid')

    symbol: str = Field(default="BTC/USDT", description="交易对象")
    timeframe: Literal['5m', '15m'] = Field(default="5m", description="入场 K 线周期")
    mode: SignalMode = Field(default=SignalMode.KEY_LEVEL, description="信号模式")
    backtest_days: int = Field(default=30, ge=1, le=3650, description="回测天数")
    cash: float = Field(default=100, ge=10, description="初始资金")
    opening_amount: float = Field(default=10, ge=0.1, description="开仓金额")
    margin_mode: MarginMode = Field(default=MarginMode.ISOLATED, description="保证金模式")
    leverage: float = Field(default=5, ge=1, le=150, description="杠杆倍数")
    maker_fee: float = Field(default=0.0002, ge=0, le=0.1, description="Maker 手续费率")
    taker_fee: float = Field(default=0.0005, ge=0, le=0.1, description="Taker 手续费率")
    slippage_rate: float = Field(default=0.0002, ge=0, le=0.1, description="滑点率")
    funding_rate: float = Field(default=0.0001, ge=0, le=0.1, description="8 小时资金费率")
    maintenance_margin_rate: float = Field(default=0.005, ge=0, le=0.1, description="维持保证金率")


class DataFetchRequest(BaseModel):
    """历史数据拉取请求参数。"""

    symbol: str = Field(default="BTC/USDT", description="交易对象")
    timeframe: str = Field(default="1h", description="K 线周期")
    days: int = Field(default=365, ge=1, le=3650, description="拉取天数")


class TradeItem(BaseModel):
    """单笔交易记录。"""

    mode: SignalMode
    strategy_source: str
    margin_mode: MarginMode
    signal_time: str
    signal_price: float
    fill_time: str
    fill_price: float
    atr_snapshot: float
    stop_price: float
    target_price: float
    expected_stop_amount: float
    expected_target_amount: float
    environment_1h: str | None
    filter_4h: str
    entry_time: str
    exit_time: str
    side: str = "long"
    entry_price: float
    exit_price: float
    size: float
    margin_amount: float = 0
    notional_amount: float = 0
    leverage: float = 1
    liquidation_price: float = 0
    funding_fee: float = 0
    entry_commission: float = 0
    exit_commission: float = 0
    pnl: float
    pnl_pct: float
    exit_reason: str = "策略平仓"
    entry_reason: str = "策略信号"
    entry_score: float = 0
    entry_context: str = ""


class EquityPoint(BaseModel):
    """权益曲线上的一个点。"""

    timestamp: str | None
    equity: float


class BacktestResponse(BaseModel):
    """回测结果响应。"""

    success: bool = True
    total_return_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None
    num_trades: int
    total_funding_fee: float = 0
    quality_score: float = 0
    quality_grade: str = "reject"
    quality_label: str = "不建议"
    quality_reasons: list[str] = Field(default_factory=list)
    profit_factor: float = 0
    avg_win_loss_ratio: float = 0
    max_consecutive_losses: int = 0
    result_path: str | None = None
    equity_curve: list[EquityPoint]
    trade_list: list[TradeItem]
    error: str | None = None


class OptimizationCandidate(BaseModel):
    """参数搜索候选结果。"""

    rank: int
    mode: SignalMode
    mode_label: str
    timeframe: Literal['5m', '15m']
    margin_mode: MarginMode
    leverage: float
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    out_sample_return_pct: float = 0
    out_sample_quality_score: float = 0
    random_pass_rate_pct: float = 0
    random_avg_return_pct: float = 0
    random_worst_return_pct: float = 0
    long_window_return_pct: float = 0
    long_window_days: int = 0
    robustness_score: float = 0
    robustness_label: str = "未验证"
    num_trades: int
    quality_score: float
    quality_grade: str
    quality_label: str
    quality_reasons: list[str]
    profit_factor: float
    avg_win_loss_ratio: float
    max_consecutive_losses: int
    score: float


class OptimizationResponse(BaseModel):
    """参数搜索响应。"""

    success: bool = True
    candidates: list[OptimizationCandidate]
    evaluated_count: int = 0
    filtered_count: int = 0
    failure_count: int = 0
    partial: bool = False
    error: str | None = None


class OptimizationJobCreated(BaseModel):
    """Background optimization job creation response."""

    success: bool = True
    job_id: str | None = None
    error: str | None = None


class OptimizationJobStatus(BaseModel):
    """Progress and result for one background optimization job."""

    success: bool = True
    job_id: str
    state: str = 'queued'
    stage: str = '等待'
    evaluated_count: int = 0
    total_budget: int = 54
    filtered_count: int = 0
    failure_count: int = 0
    elapsed_seconds: float = 0
    estimated_remaining_seconds: float = 0
    partial: bool = False
    candidates: list[OptimizationCandidate] = Field(default_factory=list)
    error: str | None = None


class DataStatus(BaseModel):
    """本地数据文件状态。"""

    symbol: str
    timeframe: str
    exists: bool
    rows: int | None = None
    file_size_kb: float | None = None


class DataFetchResponse(BaseModel):
    """历史数据拉取响应。"""

    success: bool = True
    symbol: str
    timeframe: str
    rows: int | None = None
    file_size_kb: float | None = None
    error: str | None = None
