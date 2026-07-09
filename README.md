# liang_hua

本项目是一个全自动量化交易机器人的第一阶段 MVP：在本机网页中选择交易对象、入场周期、信号模式、保证金模式和成本参数，然后使用历史 K 线数据运行回测，展示收益曲线、胜率、回撤、夏普比率和交易明细。

## 当前功能

- FastAPI Web 服务
- Jinja2 页面渲染
- Chart.js 收益曲线
- ccxt 拉取交易所 K 线数据
- CSV 本地数据缓存
- backtesting.py 回测引擎封装
- 三种稳定信号模式：`KEY_LEVEL`、`RSI_REVERSAL`、`KEY_LEVEL_RSI`
- 入场周期支持 `5m`、`15m`，并强制使用已收盘 `1h` 和 `4h` 上下文
- 确定性渐进参数搜索、样本外和随机窗口稳健性验证
- 小资金小数仓位回测，初始资金最低 10 USDT
- 支持逐仓/全仓、单笔开仓金额、杠杆、maker/taker 手续费、滑点、资金费率和维持保证金率
- 交易记录包含冻结 ATR、预期止损/止盈 USDT 金额、实际成交价、实际出场价和实际盈亏

当前策略是规则信号，不是 AI 自动交易。参数搜索已经实现，但实时行情、模拟订单、持仓同步和实盘下单尚未实现。

未通过 `scripts/validate_strategies.py` 阈值验证的模式，保持不可用于未来自动化 testnet 执行。

## 阶段状态

- 第一阶段（历史数据回测）：已完成。
- 第二阶段（模拟盘）：待开发；下一步需要实现实时行情、模拟撮合、订单与持仓状态、风控熔断和交易日志。
- 第三阶段（实盘小仓位）：未开始，必须在模拟盘验收通过后进入。

## 安装依赖

```powershell
pip install -r requirements.txt
```

## 启动 Web 服务

普通启动：

```powershell
python main.py
```

如果 Windows 终端出现中文乱码，先运行：

```powershell
.\scripts\setup_terminal.ps1
python main.py
```

也可以直接运行：

```powershell
.\scripts\start.ps1
```

如果 PowerShell 提示脚本执行被禁用，可以改用：

```cmd
scripts\start.cmd
```

或临时绕过执行策略：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

启动后打开：

```text
http://127.0.0.1:8000
```

## 拉取历史数据

```powershell
python -m src.data.fetcher --symbol BTC/USDT --timeframe 1h --days 365
```

信号模式回测需要同时存在入场周期、`1h`、`4h` 数据。例如验证 ETH/USDT 5m：

```powershell
python -m src.data.fetcher --symbol ETH/USDT --timeframe 5m --days 365
python -m src.data.fetcher --symbol ETH/USDT --timeframe 1h --days 365
python -m src.data.fetcher --symbol ETH/USDT --timeframe 4h --days 365
```

## API 请求字段

`POST /api/backtest` 和优化接口使用同一组核心字段：

| 字段 | 可选值 / 范围 | 默认值 |
|---|---:|---:|
| `symbol` | 如 `BTC/USDT`、`ETH/USDT` | `BTC/USDT` |
| `timeframe` | `5m`、`15m` | `5m` |
| `mode` | `KEY_LEVEL`、`RSI_REVERSAL`、`KEY_LEVEL_RSI` | `KEY_LEVEL` |
| `backtest_days` | `1` 到 `3650` | `30` |
| `cash` | `>= 10` | `100` |
| `opening_amount` | `>= 0.1` 且不能超过 `cash` | `10` |
| `margin_mode` | `ISOLATED`、`CROSS` | `ISOLATED` |
| `leverage` | `1` 到 `150` | `5` |
| `maker_fee` | `0` 到 `0.1` | `0.0002` |
| `taker_fee` | `0` 到 `0.1` | `0.0005` |
| `slippage_rate` | `0` 到 `0.1` | `0.0002` |
| `funding_rate` | `0` 到 `0.1` | `0.0001` |
| `maintenance_margin_rate` | `0` 到 `0.1` | `0.005` |

## 运行测试

```powershell
pytest
```

测试使用本地构造的数据，不依赖网络。

## 策略验证矩阵

```powershell
python scripts\validate_strategies.py --symbol ETH/USDT --days 365 --output docs\strategy-validation.md
```

验证脚本会对三种稳定信号模式和两种保证金模式生成 6 行结果，每行必须明确为 `通过` 或 `未通过验证`，失败原因写入 Markdown。

## 安全说明

- `.env` 已在 `.gitignore` 中忽略，不要提交真实密钥。
- `data/*.csv` 已忽略，历史行情数据可以本地重新拉取。
- 当前项目只包含回测功能，没有实盘下单逻辑。
