# 订单流数据层设计与审计规则

## 目标

先确认公开历史数据是否真实、完整、可对齐，再决定能否研究“主动成交冲击 + OI 确认”。本阶段不生成因子结论、交易策略或实盘接口。

## 数据源边界

使用 Binance Data Collection 的 USDⓈ-M Futures 公共归档，不使用 API key，不修改 `.env`。

第一阶段允许的数据集：

| 数据集 | 频率 | 用途 | 初始状态 |
|---|---|---|---|
| 增强 `klines/5m` | 5m | 正式历史层：主动买卖量、成交笔数、价格 | 必需且优先 |
| `aggTrades` | 逐笔聚合成交 | 校验主动方向解释和增强 K 线聚合口径 | 只需边界样本 |
| `metrics` | 5m | OI、持仓价值及多空比环境 | 必需 |
| `fundingRate` | 资金费结算 | 拥挤度环境标签 | 必需 |
| `bookDepth` | 官方归档粒度 | 只审计字段，不作为第一条因子必需输入 | 可选 |
| 爆仓 | 实时流 | 官方公共历史归档未确认 | 不伪造；后续只能另找可靠来源或从未来采集 |

官方月度 `aggTrades` 体积较大：2024-01 的 BTC 压缩包约 523 MB，ETH 约 419 MB；BTC/ETH 2024–2025 共 48 个月文件约 `28.04 GB` 压缩体积，解压和标准化还需要额外空间。相同日期的增强 5m K 线每天每个标的只有约 13–14 KB，并已经包含 taker buy base/quote volume。正式 5m 研究因此使用增强 K 线；首次审计仍下载 `2024-01-01` 一天 `aggTrades`，只用于验证主动方向和量守恒，不计划下载两年逐笔全量。

## 目录结构

程序生成的数据全部位于：

```text
data/order_flow/binance_um/
├── raw/
│   ├── aggTrades/{SYMBOL}/{YEAR}/
│   ├── klines_5m/{SYMBOL}/{YEAR}/
│   ├── metrics/{SYMBOL}/{YEAR}/
│   ├── fundingRate/{SYMBOL}/{YEAR}/
│   └── bookDepth/{SYMBOL}/{YEAR}/
└── normalized/
    ├── aggTrades_5m/{SYMBOL}/{YEAR}/
    ├── klines_5m/{SYMBOL}/{YEAR}/
    ├── metrics/{SYMBOL}/{YEAR}/
    ├── fundingRate/{SYMBOL}/{YEAR}/
    └── bookDepth/{SYMBOL}/{YEAR}/
```

原始 ZIP 与 `.CHECKSUM` 一起保存。标准化文件不得覆盖现有 `data/{year}/` OHLCV。

## 标准化 aggTrades 5m 字段

| 字段 | 定义 |
|---|---|
| `timestamp` | UTC 5m 桶开始时间 |
| `symbol` | `BTCUSDT` 或 `ETHUSDT` |
| `trade_count` | 聚合成交记录数 |
| `base_volume` | 成交基础币总量 |
| `quote_volume` | `price * quantity` 总和 |
| `taker_buy_base_volume` | `isBuyerMaker=false` 的数量 |
| `taker_sell_base_volume` | `isBuyerMaker=true` 的数量 |
| `taker_buy_quote_volume` | 主动买入名义金额 |
| `taker_sell_quote_volume` | 主动卖出名义金额 |
| `signed_base_volume` | 主动买量减主动卖量 |
| `order_flow_imbalance` | `(主动买量-主动卖量)/总量` |

`isBuyerMaker=true` 表示买方是 maker，因此主动方是卖方；不能反向解释。

`aggTrades` 是按单个 taker order 聚合的记录，单条聚合记录可能跨过 5m 边界，因此不能要求它重建的每个 5m 桶与 K 线完全相同。跨源校验以完整 UTC 日的总成交量和主动买量守恒为硬门槛，单桶差异只作边界诊断；正式 5m 时间归属以官方增强 K 线为准。

## 质量门槛

一个样本日只有同时满足以下条件才可标记为可用：

1. ZIP 的 SHA-256 与官方 `.CHECKSUM` 一致；
2. 时间戳可解析为 UTC，且全部属于请求日；
3. 价格、数量均为有限正数；
4. 聚合成交 ID 无重复；
5. 5m 桶完整覆盖 288 个时间点；无成交桶必须显式补零，不能删除；
6. `taker_buy_base_volume + taker_sell_base_volume == base_volume`（浮点容差内）；
7. OI `metrics` 能与 5m 桶精确对齐，缺失率必须报告；
8. 任何字段变化、缺失或覆盖异常都停止全量下载，不通过静默填充绕过。

## 第一条候选研究（暂不执行）

数据层通过后，才冻结“主动成交冲击 + OI 同向增加后的 15m 延续”事件。2024 用于规则实现，2025 独立验证，2026 保留。因子阈值不得在数据质量审计阶段提前选择。
