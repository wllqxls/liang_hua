# liang_hua

本项目是一个全自动量化交易机器人的第一阶段 MVP：在本机网页中选择交易对象、入场周期、信号模式、保证金模式和成本参数，然后使用历史 K 线数据运行回测，展示收益曲线、胜率、回撤、夏普比率和交易明细。

## 当前功能

- FastAPI Web 服务
- Jinja2 页面渲染
- Chart.js 收益曲线
- ccxt 拉取交易所 K 线数据
- 按年份组织的 CSV 本地数据缓存
- backtesting.py 回测引擎封装
- 三种稳定信号模式：`KEY_LEVEL`、`RSI_REVERSAL`、`KEY_LEVEL_RSI`
- 入场周期支持 `5m`、`15m`，并强制使用已收盘 `1h` 和 `4h` 上下文
- 确定性渐进参数搜索、样本外和随机窗口稳健性验证
- 参数搜索覆盖模式、入场周期、杠杆和有限策略参数组（RSI 阈值、ATR 止损/止盈倍数）
- 年度验证会同步生成逐笔成本、出场原因、方向和多周期环境诊断报告
- 小资金小数仓位回测，初始资金最低 10 USDT
- 支持逐仓/全仓、单笔开仓金额、杠杆、maker/taker 手续费、滑点、资金费率和维持保证金率
- 交易记录包含冻结 ATR、预期止损/止盈 USDT 金额、实际成交价、实际出场价和实际盈亏
- 本地数据面板支持选择年份后一键拉取 `5m`、`15m`、`1h`、`4h`

当前策略是规则信号，不是 AI 自动交易。参数搜索已经实现，但实时行情、模拟订单、持仓同步和实盘下单尚未实现。

未通过 `scripts/validate_strategies.py` 阈值验证的模式，保持不可用于未来自动化 testnet 执行。诊断报告只用于定位失败原因，不会降低通过标准。

## 阶段状态

- 第一阶段（历史数据回测）：回测系统已完成，当前策略尚未通过年度验证，正在进行策略诊断和重构。
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

推荐在网页“本地数据”面板中选择交易对象和年份，然后点击：

```text
拉取指定年份全部周期
```

系统会一次性拉取该年份的：

- `5m`
- `15m`
- `1h`
- `4h`

新数据保存路径为：

```text
data/{year}/{SYMBOL}_{TIMEFRAME}.csv
```

例如：

```text
data/2025/ETH_USDT_5m.csv
data/2025/ETH_USDT_15m.csv
data/2025/ETH_USDT_1h.csv
data/2025/ETH_USDT_4h.csv
```

无论从 Codex、项目目录、桌面快捷方式还是其他终端目录启动 Web 服务，系统都会把网页拉取的数据写入项目目录 `C:\KUN\liang_hua\data\{year}\`，不会写到当前启动目录。

如果同一年同一周期的数据已经存在，系统会合并新旧 CSV、按时间戳去重、排序并覆盖保存。旧的根目录 `data/ETH_USDT_5m.csv` 文件可以保留兼容，但不再是网页数据管理和新回测请求的主动入口。

## API 请求字段

`POST /api/backtest` 和优化接口使用同一组核心字段：

| 字段 | 可选值 / 范围 | 默认值 |
|---|---:|---:|
| `symbol` | 如 `BTC/USDT`、`ETH/USDT` | `BTC/USDT` |
| `timeframe` | `5m`、`15m` | `5m` |
| `data_year` | `2017` 到 `2100` | 当前年份 |
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

`POST /api/fetch-data` 只接受交易对象和年份：

```json
{
  "symbol": "ETH/USDT",
  "year": 2025
}
```

`GET /api/data-status?symbol=ETH/USDT&year=2025` 返回该年份 `5m`、`15m`、`1h`、`4h` 四个 CSV 的存在状态和真实去重行数。

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

同一次运行还会复用 6 组年度回测的逐笔交易生成 `docs/strategy-diagnostics.md`，统计手续费/资金费前收益（已含滑点）、手续费、资金费、净收益、出场原因、交易方向、1 小时环境和 4 小时过滤标签。可用 `--diagnostics-output` 指定其他诊断报告路径。

验证脚本会优先合并 `data/{year}/` 下同一币种的年份数据，生成临时验证数据到 `tmp/validation_data/`，用于覆盖 `365 天 + warmup` 的验证窗口；原始 `data/` 行情文件不会被修改。

## 安全说明

- `.env` 已在 `.gitignore` 中忽略，不要提交真实密钥。
- `data/**/*.csv` 已忽略，历史行情数据可以本地重新拉取。
- 当前项目只包含回测功能，没有实盘下单逻辑。
