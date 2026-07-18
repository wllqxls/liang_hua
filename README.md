# liang_hua

本项目当前是一个只读取本地历史数据的半自动交易研究工具：机器逐根回放 K 线并筛选候选信号，信号出现时强制暂停，由人决定开多、开空或放弃。系统不连接 testnet、实盘或实时行情。

## 当前功能

- FastAPI Web 服务
- Jinja2 页面渲染
- 本地化 TradingView Lightweight Charts K 线与人工权益曲线，断网可用
- ccxt 拉取交易所 K 线数据
- 按年份组织的 CSV 本地数据缓存
- 服务端逐 K 线手动回放状态机，浏览器不接收未来 K 线
- 三种稳定信号模式：`KEY_LEVEL`、`RSI_REVERSAL`、`KEY_LEVEL_RSI`
- 入场周期支持 `5m`、`15m`，并强制使用已收盘 `1h` 和 `4h` 上下文
- 信号出现后只提供【开空】【开多】【放弃】三种人工选择
- 人工接受的交易在下一根 K 线开盘成交，按冻结 ATR 止盈止损并计入手续费、滑点
- 页面只展示人工接受交易的权益曲线与交易明细
- 半自动因子白名单使用 2024 排序、2025 验证，硬性要求两年毛收益为正且每年 30–100 次事件
- 白名单优先按 K 线实体/ATR 和影线/ATR 的视觉辨识度排序，输出到 `results/semi_auto_factor_whitelist.csv`
- 旧自动回测、优化器和策略诊断代码仅保留为失败基线，不再出现在网页主动入口

当前候选信号是冻结规则，不是 AI 判断，也不会自动下单。候选提示只用于辅助人眼筛选。

## 阶段状态

- 当前阶段：本地历史数据半自动回放与因子白名单。
- 暂缓阶段：实时盘口、实时爆仓、testnet 与实盘对接。
- 升级条件：现有历史数据先显示明确、可复现的正期望，再单独设计后续阶段。

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

## 半自动 API

- `POST /api/manual-replays`：建立只读取本地 CSV 的回放会话。
- `POST /api/manual-replays/{session_id}/advance`：服务端向前扫描，遇到候选信号即暂停。
- `POST /api/manual-replays/{session_id}/decision`：提交 `BUY`、`SELL` 或 `SKIP` 人工决策。
- `POST /api/semi-auto-whitelist`：用 2024/2025 本地数据生成半自动因子白名单 CSV。

旧自动回测和诊断 API 为兼容历史测试继续保留，但不是网页主动入口。

## 运行测试

```powershell
pytest
```

测试使用本地构造的数据，不依赖网络。

## 旧自动验证基线

以下脚本仅用于复现过去的自动策略失败基线，不是当前半自动网页流程，也不会触发任何实盘连接。

```powershell
python scripts\validate_strategies.py --symbol ETH/USDT --days 365 --output docs\strategy-validation.md
```

验证脚本会对三种稳定信号模式和两种保证金模式生成 6 行结果，每行必须明确为 `通过` 或 `未通过验证`，失败原因写入 Markdown。

同一次运行还会复用 3 个策略模式的年度回测逐笔交易生成 `docs/strategy-diagnostics.md`，固定使用更保守的逐仓基准，统计手续费/资金费前收益（已含滑点）、手续费、资金费、净收益、出场原因、交易方向、1 小时环境和 4 小时过滤标签。可用 `--diagnostics-output` 指定其他诊断报告路径。

网页右侧的“策略诊断”页会自动读取最近一次结果，但不会自动运行完整诊断。点击“运行 365 天诊断”后，后台完成 3 个策略模式并显示进度；结构化结果保存到 `results/strategy-diagnostics.json`，Markdown 与网页数据来自同一次回测。逐仓与全仓的强平差异由独立风险测试覆盖，不重复运行年度策略验证。

验证脚本会优先合并 `data/{year}/` 下同一币种的年份数据，生成临时验证数据到 `tmp/validation_data/`，用于覆盖 `365 天 + warmup` 的验证窗口；原始 `data/` 行情文件不会被修改。

## 安全说明

- `.env` 已在 `.gitignore` 中忽略，不要提交真实密钥。
- `data/**/*.csv` 已忽略，历史行情数据可以本地重新拉取。
- 当前项目只包含回测功能，没有实盘下单逻辑。
