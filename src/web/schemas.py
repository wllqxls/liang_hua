"""
Pydantic 数据模型：API 请求/响应结构。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    """回测请求参数。"""

    symbol: str = Field(default="BTC/USDT", description="交易对")
    timeframe: str = Field(default="1h", description="K 线周期")
    strategy: str = Field(default="SRBreakout", description="策略名称")
    lookback: int = Field(default=20, ge=1, le=500, description="回溯窗口")
    cash: float = Field(default=1_000, ge=10, description="初始资金")
    commission: float = Field(default=0.001, ge=0, le=0.1, description="手续费率")


class DataFetchRequest(BaseModel):
    """历史数据拉取请求参数。"""

    symbol: str = Field(default="BTC/USDT", description="交易对")
    timeframe: str = Field(default="1h", description="K 线周期")
    days: int = Field(default=365, ge=1, le=3650, description="拉取天数")


class TradeItem(BaseModel):
    """单笔交易记录。"""

    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float


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
    equity_curve: list[EquityPoint]
    trade_list: list[TradeItem]
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
