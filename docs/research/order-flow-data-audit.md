# Order-Flow Public Data Quality Audit

- Scope: data availability and integrity only; no factor or strategy is generated.
- Source: Binance Data Collection, USDⓈ-M Futures public archives.
- Sample: BTCUSDT and ETHUSDT on UTC 2024-01-01; funding uses 2024-01 monthly archive.
- Full-history bodies were not downloaded; target coverage uses HTTP HEAD on 2024 start and 2025 end archives.
- Estimated BTC/ETH 2024–2025 monthly aggTrades download: `28.04 GB compressed`.
- Design: `docs/research/order-flow-data-design.md`.
- Code revision: `8f127c4`.

## Downloaded sample archives

| Symbol | Dataset | Period | Compressed MB | Rows | SHA-256 verified | Columns |
|---|---|---|---:|---:|---|---|
| BTCUSDT | klines_5m | 2024-01-01 | 0.01 | 288 | yes | open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore |
| BTCUSDT | aggTrades | 2024-01-01 | 9.60 | 761222 | yes | agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker |
| BTCUSDT | metrics | 2024-01-01 | 0.01 | 288 | yes | create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio |
| BTCUSDT | fundingRate | 2024-01 | 0.00 | 93 | yes | calc_time, funding_interval_hours, last_funding_rate |
| BTCUSDT | bookDepth | 2024-01-01 | 0.45 | 28800 | yes | timestamp, percentage, depth, notional |
| ETHUSDT | klines_5m | 2024-01-01 | 0.01 | 288 | yes | open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore |
| ETHUSDT | aggTrades | 2024-01-01 | 6.80 | 504953 | yes | agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker |
| ETHUSDT | metrics | 2024-01-01 | 0.01 | 288 | yes | create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio |
| ETHUSDT | fundingRate | 2024-01 | 0.00 | 93 | yes | calc_time, funding_interval_hours, last_funding_rate |
| ETHUSDT | bookDepth | 2024-01-01 | 0.47 | 28800 | yes | timestamp, percentage, depth, notional |

## aggTrades 5m normalization

| Symbol | Raw rows | Duplicate IDs | Invalid rows | Out-of-day rows | Populated 5m buckets | Missing buckets | Volume conservation max error | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| BTCUSDT | 761222 | 0 | 0 | 0 | 288 | 0 | 9.09494701773e-13 | PASS |
| ETHUSDT | 504953 | 0 | 0 | 0 | 288 | 0 | 3.63797880709e-12 | PASS |

## metrics 5m alignment

| Symbol | Rows | Duplicate timestamps | Invalid rows | Out-of-day rows | Missing 5m timestamps | Status |
|---|---:|---:|---:|---:|---:|---|
| BTCUSDT | 288 | 0 | 0 | 0 | 0 | PASS |
| ETHUSDT | 288 | 0 | 0 | 0 | 0 | PASS |

## Enhanced 5m kline order flow

| Symbol | Rows | Duplicate timestamps | Invalid rows | Out-of-day rows | Missing 5m timestamps | Base conservation error | Quote conservation error | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| BTCUSDT | 288 | 0 | 0 | 0 | 0 | 1.13686837722e-13 | 7.45058059692e-09 | PASS |
| ETHUSDT | 288 | 0 | 0 | 0 | 0 | 9.09494701773e-13 | 1.86264514923e-09 | PASS |

## aggTrades ↔ enhanced kline reconciliation

- An aggTrade represents one aggregated taker order and can straddle a 5m boundary. Per-bucket differences are diagnostic; the gate uses full-day volume conservation.

| Symbol | Matched 5m timestamps | Missing timestamps | Max bucket total error | Max bucket taker-buy error | Daily total error | Daily taker-buy error | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| BTCUSDT | 288 | 0 | 0.00151225268368 | 0.00293650971015 | 7.57663309004e-06 | 1.45814505565e-05 | PASS |
| ETHUSDT | 288 | 0 | 0.0157874690173 | 0.00108728692131 | 0 | 0 | PASS |

## Target-period boundary coverage

| Symbol | Dataset | First target | Available | Last target | Available |
|---|---|---|---|---|---|
| BTCUSDT | klines_5m | 2024-01-01 | yes | 2025-12-31 | yes |
| BTCUSDT | aggTrades | 2024-01-01 | yes | 2025-12-31 | yes |
| BTCUSDT | metrics | 2024-01-01 | yes | 2025-12-31 | yes |
| BTCUSDT | fundingRate | 2024-01 | yes | 2025-12 | yes |
| BTCUSDT | bookDepth | 2024-01-01 | yes | 2025-12-31 | yes |
| ETHUSDT | klines_5m | 2024-01-01 | yes | 2025-12-31 | yes |
| ETHUSDT | aggTrades | 2024-01-01 | yes | 2025-12-31 | yes |
| ETHUSDT | metrics | 2024-01-01 | yes | 2025-12-31 | yes |
| ETHUSDT | fundingRate | 2024-01 | yes | 2025-12 | yes |
| ETHUSDT | bookDepth | 2024-01-01 | yes | 2025-12-31 | yes |

## Gate

- Sample checksums passed: `yes`.
- aggTrades normalization passed: `yes`.
- OI metrics 5m alignment passed: `yes`.
- Enhanced 5m kline order-flow fields passed: `yes`.
- aggTrades versus enhanced kline reconciliation passed: `yes`.
- Required archive boundary coverage passed: `yes`.
- Historical liquidation archive: `not confirmed`; no liquidation field may be fabricated.
- Strategy generated: `no`.
