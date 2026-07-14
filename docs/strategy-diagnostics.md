# Strategy Failure Diagnostics

- Symbol: `ETH/USDT`
- Timeframe: `5m`
- Annual window: `365` days
- Initial cash: `100 USDT`
- Opening margin: `10 USDT`
- Leverage: `5x`
- Taker fee: `0.0500%` per fill
- Slippage: `0.0200%` per fill
- Funding rate: `0.0100%` per 8 hours

本报告复用验证矩阵的同一次年度回测。手续费/资金费前收益由逐笔净收益加回手续费、扣除资金费净现金流得到，其中已经包含滑点影响；资金费为正表示账户收到，负数表示账户支付。

## Summary

| Mode | Margin | Trades | Win Rate % | Pre-fee PnL (slippage included) | Commission | Funding Cash Flow | Net Fee/Funding Cost | Net PnL | Pre-fee PF | Net PF | Avg Net/Trade | Fee/Funding Cost to Pre-fee Gross Profit % |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| KEY_LEVEL | ISOLATED | 1505 | 31.23 | -14.8002 | 75.2501 | 0.0150 | 75.2351 | -90.0353 | 0.86 | 0.43 | -0.0598 | 81.71 |
| KEY_LEVEL | CROSS | 1505 | 31.23 | -14.8002 | 75.2501 | 0.0150 | 75.2351 | -90.0353 | 0.86 | 0.43 | -0.0598 | 81.71 |
| RSI_REVERSAL | ISOLATED | 49 | 28.57 | -0.6105 | 2.4513 | 0.0050 | 2.4463 | -3.0568 | 0.81 | 0.39 | -0.0624 | 92.68 |
| RSI_REVERSAL | CROSS | 49 | 28.57 | -0.6105 | 2.4513 | 0.0050 | 2.4463 | -3.0568 | 0.81 | 0.39 | -0.0624 | 92.68 |
| KEY_LEVEL_RSI | ISOLATED | 1507 | 31.25 | -14.7166 | 75.3501 | 0.0150 | 75.3351 | -90.0517 | 0.86 | 0.43 | -0.0598 | 81.65 |
| KEY_LEVEL_RSI | CROSS | 1507 | 31.25 | -14.7166 | 75.3501 | 0.0150 | 75.3351 | -90.0517 | 0.86 | 0.43 | -0.0598 | 81.65 |

## Cross-mode Findings

- `ISOLATED` 下 KEY_LEVEL_RSI 相比 KEY_LEVEL 的交易数变化 +0.13%（1505 -> 1507），净收益变化 -0.0164 USDT。组合模式没有形成实质性的交易筛选。
- `CROSS` 下 KEY_LEVEL_RSI 相比 KEY_LEVEL 的交易数变化 +0.13%（1505 -> 1507），净收益变化 -0.0164 USDT。组合模式没有形成实质性的交易筛选。
- `KEY_LEVEL` 的 ISOLATED 与 CROSS 结果相同，说明当前失败不是由保证金模式差异造成。
- `RSI_REVERSAL` 的 ISOLATED 与 CROSS 结果相同，说明当前失败不是由保证金模式差异造成。
- `KEY_LEVEL_RSI` 的 ISOLATED 与 CROSS 结果相同，说明当前失败不是由保证金模式差异造成。

## KEY_LEVEL / ISOLATED

- 在计入滑点、但尚未扣除手续费和资金费时已亏损 14.8002 USDT，说明进出场结构在真实成交条件下没有足够优势，失败不只由手续费造成。
- 1505 笔交易共产生 75.2501 USDT 手续费，平均每笔净收益 -0.0598 USDT。
- 日均交易 4.12 笔，交易频率较高，手续费会被持续放大。
- 手续费与资金费净成本占手续费前盈利交易总额的 81.71%。
- 止损 1035 笔、止盈 470 笔；止损桶净收益 -158.6246 USDT，止盈桶净收益 68.5894 USDT。
- 4 小时环境中 `FILTER_SHORT` 亏损最多：774 笔合计 -46.7539 USDT。
- 方向上 `long` 亏损最多：770 笔合计 -45.9204 USDT。

### Exit Reason

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| STOP | 1035 | 0.00 | -106.8761 | 51.7486 | -158.6246 | 0.00 | -0.1533 |
| TARGET | 470 | 100.00 | 92.0759 | 23.4866 | 68.5894 | 99.00 | 0.1459 |

### Side

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| long | 770 | 30.65 | -7.2740 | 38.6464 | -45.9204 | 0.40 | -0.0596 |
| short | 735 | 31.84 | -7.5261 | 36.5888 | -44.1149 | 0.46 | -0.0600 |

### 1h Environment

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| BUY | 770 | 30.65 | -7.2740 | 38.6464 | -45.9204 | 0.40 | -0.0596 |
| SELL | 735 | 31.84 | -7.5261 | 36.5888 | -44.1149 | 0.46 | -0.0600 |

### 4h Filter

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| FILTER_LONG | 731 | 31.05 | -6.7108 | 36.5706 | -43.2814 | 0.41 | -0.0592 |
| FILTER_SHORT | 774 | 31.40 | -8.0894 | 38.6645 | -46.7539 | 0.45 | -0.0604 |

## KEY_LEVEL / CROSS

- 在计入滑点、但尚未扣除手续费和资金费时已亏损 14.8002 USDT，说明进出场结构在真实成交条件下没有足够优势，失败不只由手续费造成。
- 1505 笔交易共产生 75.2501 USDT 手续费，平均每笔净收益 -0.0598 USDT。
- 日均交易 4.12 笔，交易频率较高，手续费会被持续放大。
- 手续费与资金费净成本占手续费前盈利交易总额的 81.71%。
- 止损 1035 笔、止盈 470 笔；止损桶净收益 -158.6246 USDT，止盈桶净收益 68.5894 USDT。
- 4 小时环境中 `FILTER_SHORT` 亏损最多：774 笔合计 -46.7539 USDT。
- 方向上 `long` 亏损最多：770 笔合计 -45.9204 USDT。

### Exit Reason

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| STOP | 1035 | 0.00 | -106.8761 | 51.7486 | -158.6246 | 0.00 | -0.1533 |
| TARGET | 470 | 100.00 | 92.0759 | 23.4866 | 68.5894 | 99.00 | 0.1459 |

### Side

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| long | 770 | 30.65 | -7.2740 | 38.6464 | -45.9204 | 0.40 | -0.0596 |
| short | 735 | 31.84 | -7.5261 | 36.5888 | -44.1149 | 0.46 | -0.0600 |

### 1h Environment

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| BUY | 770 | 30.65 | -7.2740 | 38.6464 | -45.9204 | 0.40 | -0.0596 |
| SELL | 735 | 31.84 | -7.5261 | 36.5888 | -44.1149 | 0.46 | -0.0600 |

### 4h Filter

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| FILTER_LONG | 731 | 31.05 | -6.7108 | 36.5706 | -43.2814 | 0.41 | -0.0592 |
| FILTER_SHORT | 774 | 31.40 | -8.0894 | 38.6645 | -46.7539 | 0.45 | -0.0604 |

## RSI_REVERSAL / ISOLATED

- 在计入滑点、但尚未扣除手续费和资金费时已亏损 0.6105 USDT，说明进出场结构在真实成交条件下没有足够优势，失败不只由手续费造成。
- 49 笔交易共产生 2.4513 USDT 手续费，平均每笔净收益 -0.0624 USDT。
- 手续费与资金费净成本占手续费前盈利交易总额的 92.68%。
- 止损 35 笔、止盈 14 笔；止损桶净收益 -5.0001 USDT，止盈桶净收益 1.9433 USDT。
- 4 小时环境中 `FILTER_SHORT` 亏损最多：37 笔合计 -2.0132 USDT。
- 方向上 `short` 亏损最多：18 笔合计 -2.4786 USDT。

### Exit Reason

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| STOP | 35 | 0.00 | -3.2499 | 1.7502 | -5.0001 | 0.00 | -0.1429 |
| TARGET | 14 | 100.00 | 2.6394 | 0.6961 | 1.9433 | 99.00 | 0.1388 |

### Side

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| long | 31 | 38.71 | 0.9723 | 1.5505 | -0.5782 | 0.76 | -0.0187 |
| short | 18 | 11.11 | -1.5828 | 0.8958 | -2.4786 | 0.05 | -0.1377 |

### 1h Environment

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| BUY | 31 | 38.71 | 0.9723 | 1.5505 | -0.5782 | 0.76 | -0.0187 |
| SELL | 18 | 11.11 | -1.5828 | 0.8958 | -2.4786 | 0.05 | -0.1377 |

### 4h Filter

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| FILTER_LONG | 12 | 16.67 | -0.4438 | 0.5998 | -1.0436 | 0.16 | -0.0870 |
| FILTER_SHORT | 37 | 32.43 | -0.1667 | 1.8465 | -2.0132 | 0.46 | -0.0544 |

## RSI_REVERSAL / CROSS

- 在计入滑点、但尚未扣除手续费和资金费时已亏损 0.6105 USDT，说明进出场结构在真实成交条件下没有足够优势，失败不只由手续费造成。
- 49 笔交易共产生 2.4513 USDT 手续费，平均每笔净收益 -0.0624 USDT。
- 手续费与资金费净成本占手续费前盈利交易总额的 92.68%。
- 止损 35 笔、止盈 14 笔；止损桶净收益 -5.0001 USDT，止盈桶净收益 1.9433 USDT。
- 4 小时环境中 `FILTER_SHORT` 亏损最多：37 笔合计 -2.0132 USDT。
- 方向上 `short` 亏损最多：18 笔合计 -2.4786 USDT。

### Exit Reason

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| STOP | 35 | 0.00 | -3.2499 | 1.7502 | -5.0001 | 0.00 | -0.1429 |
| TARGET | 14 | 100.00 | 2.6394 | 0.6961 | 1.9433 | 99.00 | 0.1388 |

### Side

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| long | 31 | 38.71 | 0.9723 | 1.5505 | -0.5782 | 0.76 | -0.0187 |
| short | 18 | 11.11 | -1.5828 | 0.8958 | -2.4786 | 0.05 | -0.1377 |

### 1h Environment

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| BUY | 31 | 38.71 | 0.9723 | 1.5505 | -0.5782 | 0.76 | -0.0187 |
| SELL | 18 | 11.11 | -1.5828 | 0.8958 | -2.4786 | 0.05 | -0.1377 |

### 4h Filter

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| FILTER_LONG | 12 | 16.67 | -0.4438 | 0.5998 | -1.0436 | 0.16 | -0.0870 |
| FILTER_SHORT | 37 | 32.43 | -0.1667 | 1.8465 | -2.0132 | 0.46 | -0.0544 |

## KEY_LEVEL_RSI / ISOLATED

- 在计入滑点、但尚未扣除手续费和资金费时已亏损 14.7166 USDT，说明进出场结构在真实成交条件下没有足够优势，失败不只由手续费造成。
- 1507 笔交易共产生 75.3501 USDT 手续费，平均每笔净收益 -0.0598 USDT。
- 日均交易 4.13 笔，交易频率较高，手续费会被持续放大。
- 手续费与资金费净成本占手续费前盈利交易总额的 81.65%。
- 止损 1036 笔、止盈 471 笔；止损桶净收益 -158.7780 USDT，止盈桶净收益 68.7264 USDT。
- 4 小时环境中 `FILTER_SHORT` 亏损最多：778 笔合计 -47.0124 USDT。
- 方向上 `long` 亏损最多：772 笔合计 -46.0261 USDT。

### Exit Reason

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| STOP | 1036 | 0.00 | -106.9796 | 51.7984 | -158.7780 | 0.00 | -0.1533 |
| TARGET | 471 | 100.00 | 92.2630 | 23.5367 | 68.7264 | 99.00 | 0.1459 |

### Side

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| long | 772 | 30.70 | -7.2797 | 38.7464 | -46.0261 | 0.40 | -0.0596 |
| short | 735 | 31.84 | -7.4369 | 36.5887 | -44.0256 | 0.46 | -0.0599 |

### 1h Environment

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| BUY | 772 | 30.70 | -7.2797 | 38.7464 | -46.0261 | 0.40 | -0.0596 |
| SELL | 735 | 31.84 | -7.4369 | 36.5887 | -44.0256 | 0.46 | -0.0599 |

### 4h Filter

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| FILTER_LONG | 729 | 31.14 | -6.5686 | 36.4707 | -43.0393 | 0.41 | -0.0590 |
| FILTER_SHORT | 778 | 31.36 | -8.1480 | 38.8644 | -47.0124 | 0.45 | -0.0604 |

## KEY_LEVEL_RSI / CROSS

- 在计入滑点、但尚未扣除手续费和资金费时已亏损 14.7166 USDT，说明进出场结构在真实成交条件下没有足够优势，失败不只由手续费造成。
- 1507 笔交易共产生 75.3501 USDT 手续费，平均每笔净收益 -0.0598 USDT。
- 日均交易 4.13 笔，交易频率较高，手续费会被持续放大。
- 手续费与资金费净成本占手续费前盈利交易总额的 81.65%。
- 止损 1036 笔、止盈 471 笔；止损桶净收益 -158.7780 USDT，止盈桶净收益 68.7264 USDT。
- 4 小时环境中 `FILTER_SHORT` 亏损最多：778 笔合计 -47.0124 USDT。
- 方向上 `long` 亏损最多：772 笔合计 -46.0261 USDT。

### Exit Reason

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| STOP | 1036 | 0.00 | -106.9796 | 51.7984 | -158.7780 | 0.00 | -0.1533 |
| TARGET | 471 | 100.00 | 92.2630 | 23.5367 | 68.7264 | 99.00 | 0.1459 |

### Side

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| long | 772 | 30.70 | -7.2797 | 38.7464 | -46.0261 | 0.40 | -0.0596 |
| short | 735 | 31.84 | -7.4369 | 36.5887 | -44.0256 | 0.46 | -0.0599 |

### 1h Environment

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| BUY | 772 | 30.70 | -7.2797 | 38.7464 | -46.0261 | 0.40 | -0.0596 |
| SELL | 735 | 31.84 | -7.4369 | 36.5887 | -44.0256 | 0.46 | -0.0599 |

### 4h Filter

| Bucket | Trades | Win Rate % | Pre-fee PnL (slippage included) | Net Fee/Funding Cost | Net PnL | Net PF | Avg Net/Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| FILTER_LONG | 729 | 31.14 | -6.5686 | 36.4707 | -43.0393 | 0.41 | -0.0590 |
| FILTER_SHORT | 778 | 31.36 | -8.1480 | 38.8644 | -47.0124 | 0.45 | -0.0604 |
