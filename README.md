# liang_hua

本项目是一个全自动量化交易机器人的第一阶段 MVP：在本机网页中选择交易对象、周期、策略和参数，然后使用历史 K 线数据运行回测，展示收益曲线、胜率、回撤、夏普比率和交易明细。

## 当前功能

- FastAPI Web 服务
- Jinja2 页面渲染
- Chart.js 收益曲线
- ccxt 拉取交易所 K 线数据
- CSV 本地数据缓存
- backtesting.py 回测引擎封装
- 支撑阻力突破、均线金叉死叉、RSI 超卖反弹等规则策略
- 确定性渐进参数搜索、样本外和随机窗口稳健性验证
- 小资金小数仓位回测，初始资金最低 10 USDT
- 支持单笔逐仓金额、杠杆、USDT 金额止盈止损、maker/taker 手续费参数

当前策略是规则策略，不是 AI 自动交易。参数搜索已经实现，但实时行情、模拟订单、持仓同步和实盘下单尚未实现。

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

## 运行测试

```powershell
pytest
```

测试使用本地构造的数据，不依赖网络。

## 安全说明

- `.env` 已在 `.gitignore` 中忽略，不要提交真实密钥。
- `data/*.csv` 已忽略，历史行情数据可以本地重新拉取。
- 当前项目只包含回测功能，没有实盘下单逻辑。
