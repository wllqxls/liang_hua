"""
Pydantic 数据模型：API 请求/响应结构。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    """回测请求参数。"""

    symbol: str = Field(default="BTC/USDT", description="交易对象")
    timeframe: str = Field(default="5m", description="入场 K 线周期")
    context_timeframe: str = Field(default="15m", description="环境 K 线周期")
    strategy: str = Field(default="KeyLevelScoring", description="策略名称")
    backtest_days: int = Field(default=30, ge=1, le=3650, description="回测天数")
    context_lookback: int = Field(default=192, ge=1, le=500, description="环境回溯窗口")
    entry_lookback: int = Field(default=30, ge=1, le=500, description="入场回溯窗口")
    lookback: int = Field(default=30, ge=1, le=500, description="兼容旧版回溯窗口")
    cash: float = Field(default=100, ge=10, description="初始资金")
    position_amount: float = Field(default=10, ge=0.1, description="单笔逐仓保证金")
    leverage: float = Field(default=5, ge=1, le=150, description="杠杆倍数")
    take_profit_amount: float = Field(default=1, ge=0, description="止盈金额")
    stop_loss_amount: float = Field(default=1, ge=0, description="止损金额")
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
    strategy: str
    strategy_label: str
    lookback: int
    context_lookback: int
    entry_lookback: int
    leverage: float
    take_profit_amount: float
    stop_loss_amount: float
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    out_sample_return_pct: float = 0
    out_sample_quality_score: float = 0
    random_pass_rate_pct: float = 0
    random_avg_return_pct: float = 0
    random_worst_return_pct: float = 0
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
