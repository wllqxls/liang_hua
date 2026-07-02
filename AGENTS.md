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
| 策略参数搜索 | 确定性渐进搜索 | 已实现粗筛、精搜和稳健性验证 |

## 目录结构

```
liang_hua/
├── AGENTS.md              # 项目规则（本文件）
├── requirements.txt       # Python 依赖
├── .env.example           # 环境变量模板（可提交）
├── .env                   # 真实密钥（git 忽略）
├── .gitignore
├── main.py                # FastAPI 入口
├── src/
│   ├── __init__.py
│   ├── data/
│   │   ├── __init__.py
│   │   └── fetcher.py     # 从交易所拉 K 线数据
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── engine.py      # 回测引擎封装
│   │   └── optimizer.py   # 渐进式参数搜索
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── sr_breakout.py # 支撑位阻力位突破策略
│   │   ├── ma_cross.py
│   │   ├── rsi_reversion.py
│   │   ├── key_level_scoring.py
│   │   └── risk.py        # 仓位及止盈止损换算
│   └── web/
│       ├── __init__.py
│       ├── routes.py      # FastAPI 路由
│       └── schemas.py     # Pydantic 数据模型
├── templates/
│   ├── base.html          # 公共布局
│   └── backtest.html      # 回测主页面
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── backtest.js    # 前端交互逻辑
├── data/                  # 历史 K 线 CSV 文件（git 忽略）
│   └── .gitkeep
└── tests/
    ├── __init__.py
    ├── test_fetcher.py
    ├── test_engine.py
    └── test_strategies.py
```

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

### 数据
- K 线数据 CSV 列：`timestamp, open, high, low, close, volume`
- 时间戳用 ISO 8601 字符串（`2024-01-01T00:00:00`）
- 数据文件命名：`{SYMBOL}_{TIMEFRAME}.csv`，如 `BTC_USDT_1h.csv`
- SYMBOL 中 `/` 替换为 `_`

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

## 运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Web 服务
python main.py

# 运行测试
pytest

# 单独拉数据
python -m src.data.fetcher
```

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
