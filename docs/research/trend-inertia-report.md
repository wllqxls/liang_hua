# Short-Term Trend Inertia Event Factor Report

- Scope: read-only event research; no strategy or trade is created.
- Event threshold: three same-sign close returns and cumulative absolute return >= `0.0030`.
- Fixed round-trip cost: `0.0014`.
- Conversion: gross directional return > 0 at the exact 5m, 15m, or 1h horizon.
- 15m event 5m labels come from synchronized raw 5m closes.
- Design: `docs/research/trend-inertia-design.md`.
- Code revision: `0f54b49`.

## 5m event results

| Slice | Horizon | Samples | Gross continuation % | Avg gross return % | Avg net return % | Net Profit Factor | Status |
|---|---|---:|---:|---:|---:|---:|---|
| BTC/USDT 2024 | 5m | 5929 | 47.02 | -0.0003 | -0.1403 | 0.195 | COMPLETE_YEAR |
| BTC/USDT 2024 | 15m | 5929 | 45.94 | -0.0053 | -0.1453 | 0.341 | COMPLETE_YEAR |
| BTC/USDT 2024 | 1h | 5929 | 46.11 | -0.0045 | -0.1445 | 0.565 | COMPLETE_YEAR |
| BTC/USDT 2025 | 5m | 4445 | 45.56 | -0.0077 | -0.1477 | 0.151 | COMPLETE_YEAR |
| BTC/USDT 2025 | 15m | 4445 | 46.30 | -0.0087 | -0.1487 | 0.295 | COMPLETE_YEAR |
| BTC/USDT 2025 | 1h | 4445 | 47.40 | -0.0107 | -0.1507 | 0.520 | COMPLETE_YEAR |
| ETH/USDT 2024 | 5m | 7327 | 45.67 | 0.0004 | -0.1396 | 0.227 | COMPLETE_YEAR |
| ETH/USDT 2024 | 15m | 7327 | 45.71 | -0.0046 | -0.1446 | 0.380 | COMPLETE_YEAR |
| ETH/USDT 2024 | 1h | 7327 | 46.98 | 0.0015 | -0.1385 | 0.607 | COMPLETE_YEAR |
| ETH/USDT 2025 | 5m | 8232 | 46.22 | -0.0039 | -0.1439 | 0.224 | COMPLETE_YEAR |
| ETH/USDT 2025 | 15m | 8232 | 46.49 | -0.0015 | -0.1415 | 0.402 | COMPLETE_YEAR |
| ETH/USDT 2025 | 1h | 8232 | 48.03 | 0.0005 | -0.1395 | 0.622 | COMPLETE_YEAR |

## 15m event results

| Slice | Horizon | Samples | Gross continuation % | Avg gross return % | Avg net return % | Net Profit Factor | Status |
|---|---|---:|---:|---:|---:|---:|---|
| BTC/USDT 2024 | 5m | 3212 | 44.96 | -0.0037 | -0.1437 | 0.145 | COMPLETE_YEAR |
| BTC/USDT 2024 | 15m | 3212 | 44.05 | -0.0063 | -0.1463 | 0.293 | COMPLETE_YEAR |
| BTC/USDT 2024 | 1h | 3212 | 44.74 | -0.0135 | -0.1535 | 0.492 | COMPLETE_YEAR |
| BTC/USDT 2025 | 5m | 2745 | 43.28 | -0.0066 | -0.1466 | 0.140 | COMPLETE_YEAR |
| BTC/USDT 2025 | 15m | 2745 | 45.21 | -0.0102 | -0.1502 | 0.246 | COMPLETE_YEAR |
| BTC/USDT 2025 | 1h | 2745 | 47.36 | -0.0225 | -0.1625 | 0.423 | COMPLETE_YEAR |
| ETH/USDT 2024 | 5m | 3586 | 44.79 | -0.0056 | -0.1456 | 0.183 | COMPLETE_YEAR |
| ETH/USDT 2024 | 15m | 3586 | 46.32 | 0.0061 | -0.1339 | 0.375 | COMPLETE_YEAR |
| ETH/USDT 2024 | 1h | 3586 | 45.98 | -0.0114 | -0.1514 | 0.543 | COMPLETE_YEAR |
| ETH/USDT 2025 | 5m | 3696 | 44.53 | 0.0004 | -0.1396 | 0.250 | COMPLETE_YEAR |
| ETH/USDT 2025 | 15m | 3696 | 43.53 | -0.0124 | -0.1524 | 0.365 | COMPLETE_YEAR |
| ETH/USDT 2025 | 1h | 3696 | 46.89 | -0.0038 | -0.1438 | 0.589 | COMPLETE_YEAR |
