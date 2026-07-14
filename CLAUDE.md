# liang_hua — 全自动量化交易机器人

## 项目目标

三阶段递进：**回测验证 → 模拟盘 → 实盘小仓位**。

MVP（第一阶段）：在本机浏览器打开网页，选币种、选策略、调参数，点击运行后在历史数据上回测，看到收益曲线和统计指标。

## 技术栈

| 层 | 选型 | 说明 |
|---|------|------|
| 语言 | Python 3.11+ | 全栈 Python，前端用模板 |
| 数据获取 | `ccxt` | 统一交易所 API，主用币安 |
| 回测引擎 | `backtesting.py` | 逐 K 线事件驱动回测 |
| 数据存储 | CSV（data/ 目录） | 简单、可查看、断网可用 |
| Web 后端 | `FastAPI` | REST API + Jinja2 模板渲染 |
| Web 前端 | HTML + Chart.js + 少量原生 JS | 轻量，无框架依赖 |
| 图表 | Chart.js（K线/收益曲线） | CDN 引入，不打包 |
| 实时行情 | FastAPI WebSocket（第二阶段，未实现） | 推送实时价格到浏览器 |
| 策略参数搜索 | 确定性渐进搜索 | 已实现粗筛、精搜、有限策略参数组和稳健性验证 |

## 目录结构

```
liang_hua/
├── CLAUDE.md              # 项目规则（本文件）
├── requirements.txt       # Python 依赖
├── .env.example           # 环境变量模板（可提交）
├── .env                   # 真实密钥（git 忽略）
├── .gitignore
├── main.py                # FastAPI 入口
├── scripts/
│   └── validate_strategies.py # 稳定信号模式验证矩阵
├── docs/
│   ├── strategy-validation.md # 最近一次策略验证报告
│   └── strategy-diagnostics.md # 最近一次策略失败诊断报告
├── src/
│   ├── __init__.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── fetcher.py     # 从交易所拉 K 线数据
│   │   └── yearly.py      # 按年份一键拉取多周期数据
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── diagnostics.py # 逐笔交易成本、出场和市场环境诊断
│   │   ├── engine.py      # 回测引擎封装
│   │   ├── optimizer.py   # 渐进式参数搜索
│   │   └── signal_simulator.py # 信号模式成交/出场模拟
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── signal_models.py
│   │   ├── signal_dispatcher.py
│   │   ├── signal_evaluators.py
│   │   ├── market_context.py
│   │   ├── indicators.py
│   │   └── risk.py        # 仓位及风险换算
│   └── web/
│       ├── __init__.py
│       ├── routes.py      # FastAPI 路由
│       └── schemas.py     # Pydantic 数据模型
├── templates/
│   └── backtest.html      # 回测与策略诊断双页面容器
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── backtest.js    # 前端交互逻辑
├── data/                  # 历史 K 线 CSV 文件（git 忽略）
│   ├── .gitkeep
│   └── {year}/            # 年份数据目录，如 data/2025/
└── tests/
    ├── __init__.py
    ├── test_fetcher.py
    ├── test_engine.py
    ├── test_strategies.py
    └── test_validation_script.py
```

## 当前入口模式

只允许以下信号模式作为 Web、API、优化器和验证脚本的主动入口：

- `KEY_LEVEL`
- `RSI_REVERSAL`
- `KEY_LEVEL_RSI`

保证金模式只允许：

- `ISOLATED`
- `CROSS`

`SRBreakout`、`MovingAverageCross`、`RSIReversion`、`KeyLevelScoring` 等旧类文件可以保留，但不能重新注册为主动入口策略。

## 编码约定

### Python
- 类型注解：所有函数参数和返回值必须有类型注解
- 命名：函数/变量用 `snake_case`，类用 `PascalCase`
- 字符串：单引号用于代码内字符串，双引号用于文档字符串和用户可见文本
- 文件头：不需要编码声明和 shebang（除非是入口脚本）
- 日志：用 `logging` 模块，不用 `print`
- 错误处理：捕获具体异常类型，不用裸 `except`
- 配置：所有可配置项走 `pydantic-settings` 或环境变量

### 前端
- HTML/CSS/JS 全部手写，不引入前端框架
- Chart.js 通过 CDN 引入
- JS 用原生 DOM API，不引入 jQuery
- CSS 用 CSS 变量管理颜色主题
- 所有 API 调用加 loading/error 状态处理
- `/` 使用同一 DOM 内的左右双页面：左侧为回测，右侧为策略诊断；通过边缘方向按钮平滑切换，切换时不得刷新页面或清空已填写状态
- 策略诊断必须是独立页面区域，不嵌套在回测面板内；桌面和窄屏都必须能从两侧来回切换

### 数据
- K 线数据 CSV 列：`timestamp, open, high, low, close, volume`
- 时间戳用 ISO 8601 字符串（`2024-01-01T00:00:00`）
- 新数据文件路径：`data/{year}/{SYMBOL}_{TIMEFRAME}.csv`，如 `data/2025/BTC_USDT_1h.csv`
- Web 服务和本地 Python 默认数据根目录固定为项目根目录下的 `data/`，不能随启动终端目录变化
- 网页数据管理只主动拉取 `5m`、`15m`、`1h`、`4h`
- 点击拉取指定年份数据时必须一次性拉取上述 4 个周期
- 同一年同一周期重复拉取时必须合并新旧 CSV，按时间戳去重、排序并覆盖保存
- 根目录旧文件如 `data/BTC_USDT_1h.csv` 可以保留兼容，但不是新功能主动入口
- SYMBOL 中 `/` 替换为 `_`
- 信号模式回测必须从所选 `data_year` 目录读取入场周期、`1h`、`4h` 已收盘上下文数据
- 策略验证脚本可合并 `data/{year}/` 年份目录生成 `tmp/validation_data/` 临时验证数据，用于覆盖 `365 天 + warmup`
- `data/` 下行情文件由程序写入，git 忽略，不纳入提交

### 安全红线
- `.env` 在 `.gitignore` 中，绝对不能提交
- API key/secret 只从环境变量读取
- 实盘下单接口必须有资金上限保护
- 模拟盘和实盘环境必须通过配置隔离

### 测试
- `pytest` 框架
- 测试数据用 fixtures，不依赖网络
- 回测相关测试用人工构造的小数据集
- 每个模块改完就跑相关测试
- 策略验证报告用真实本地行情数据生成，输出到 `docs/strategy-validation.md`
- 策略诊断报告必须复用同一次年度回测的逐笔交易，输出到 `docs/strategy-diagnostics.md`，不能为诊断重复运行或修改交易逻辑

## 运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Web 服务
python main.py

# 运行测试
pytest

# 运行完整测试
C:\KUN\liang_hua\.venv\Scripts\python.exe -m pytest -q

# 推荐在网页“本地数据”面板选择年份后点击：
# 拉取指定年份全部周期

# 生成策略验证矩阵
C:\KUN\liang_hua\.venv\Scripts\python.exe scripts\validate_strategies.py --symbol ETH/USDT --days 365 --output docs\strategy-validation.md
# 同一次运行自动生成 docs\strategy-diagnostics.md
```

## 策略验证规则

`scripts/validate_strategies.py` 必须覆盖 3 个信号模式，固定使用更保守的 `ISOLATED` 作为策略验证基准。

保证金模式不是策略有效性的重复验证维度。`ISOLATED` 与 `CROSS` 的信号、止盈和止损完全相同，差异只在强平抵押资金；两者的强平差异由模拟器单元测试和独立风险压力测试验证，不能复制整套年度策略验证。

每个组合必须运行：

- 12 个不重叠的 30 天窗口
- 1 个 365 天窗口
- 固定使用 taker 手续费率 `0.0005`、单次成交滑点率 `0.0002`、每 8 小时资金费率 `0.0001`

只有同时满足以下阈值才可标记为 `通过`：

- 平均窗口收益为正
- 最差窗口收益大于 `-40%`
- 全年收益为正
- 最大回撤小于 `30%`
- Profit Factor 大于等于 `1.05`
- 年化交易次数大于等于 `50`

未通过验证的模式保持不可用于未来自动化 testnet 执行。

每次完整验证还必须生成失败诊断，至少包含：

- 成本前收益、手续费、资金费净现金流、成本后净收益
- 成本前与成本后 Profit Factor、胜率和平均每笔净收益
- 按出场原因、交易方向、1 小时环境和 4 小时过滤标签拆分的交易次数与净收益
- 基于客观统计生成失败原因，不允许用诊断结果放宽上述通过阈值

### Web 策略诊断

- 普通回测、页面启动和页面切换不得自动运行完整策略诊断
- 用户必须在策略诊断页主动启动 365 天诊断；启动后由后台任务自动完成 3 个信号模式
- 前端必须显示任务阶段、已完成组合数、总组合数、耗时和错误状态，并轮询后台任务，不能让单次 HTTP 请求阻塞到验证结束
- 同一进程同时只允许一个策略诊断任务运行，重复启动必须返回明确提示
- 最新诊断结果以结构化 JSON 保存到 `results/strategy-diagnostics.json`，页面打开时自动读取最近结果
- 结构化结果必须来自生成 Markdown 报告的同一次年度回测，不允许为前端重复运行回测或解析 Markdown 表格
- 策略诊断页至少展示 3 个信号模式的验证状态、核心收益/成本指标、跨模式结论和每组主要失败原因

## 开发流程

1. 新功能先在 `src/` 写核心逻辑
2. 加对应的测试
3. 在 `src/web/routes.py` 加 API 端点
4. 在 `templates/` 和 `static/` 加前端页面
5. 验证：`pytest` 全绿 + 浏览器手动测试
6. 每次更改完成并验证通过后，主动创建内容明确的 Git commit
7. `git push` 必须先取得用户本次明确授权；禁止 force push

## 禁止事项

- 不要在代码里硬编码 API key
- 不要在回测中使用未来数据（look-ahead bias）
- 不要注释掉测试让它们通过
- 不要直接修改 `data/` 目录下的 CSV 文件（只允许程序写入）
- 不要在没有回测验证的情况下直接实盘
