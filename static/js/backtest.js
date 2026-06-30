/**
 * 量化回测系统 — 前端交互
 */

let equityChart = null;
let chartData = null;
let optimizationCandidates = [];
const MIN_NOTIONAL_BY_SYMBOL = {
    'BTC/USDT': 50,
    'ETH/USDT': 20,
    'BNB/USDT': 5,
    'SOL/USDT': 5,
    'XRP/USDT': 5,
    'ADA/USDT': 5,
    'DOGE/USDT': 5,
    'AVAX/USDT': 5,
};
const LEVERAGE_OPTIONS = [1, 2, 3, 5, 10, 20, 50, 100, 125, 150];

window.addEventListener('DOMContentLoaded', () => {
    updateStrategyDescription();
    document.getElementById('strategy').addEventListener('change', updateStrategyDescription);
    bindRealtimeChecks();
    updateOrderCheck();
    loadDataStatus();
});

// ============================================================
// 回测
// ============================================================

async function runBacktest() {
    const btn = document.getElementById('run-btn');
    const status = document.getElementById('status');
    const results = document.getElementById('results');
    const errorMsg = document.getElementById('error-msg');

    // UI：加载状态
    btn.disabled = true;
    btn.textContent = '⏳ 回测中...';
    status.innerHTML = '<span class="spinner"></span>正在计算...';
    errorMsg.classList.add('hidden');
    results.classList.add('hidden');

    const payload = collectBacktestPayload();
    const validationError = validateBacktestPayload(payload);
    if (validationError) {
        showError(validationError);
        btn.disabled = false;
        btn.textContent = '▶ 开始回测';
        return;
    }

    try {
        const resp = await fetch('/api/backtest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const data = await resp.json();

        if (!resp.ok) {
            showError(formatApiError(data));
            return;
        }

        if (!data.success) {
            showError(data.error || '回测失败');
            return;
        }

        displayResults(data);
        status.textContent = '✅ 回测完成';

    } catch (err) {
        showError('运行错误: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '▶ 开始回测';
    }
}


function validateBacktestPayload(payload) {
    if (payload.lookback < 1 || payload.lookback > 500) {
        return '回溯窗口必须在 1 到 500 之间';
    }
    if (payload.backtest_days < 1 || payload.backtest_days > 3650) {
        return '回测天数必须在 1 到 3650 之间';
    }
    if (payload.context_timeframe === payload.timeframe) {
        return '环境周期和入场周期建议分开，例如 15m + 5m';
    }
    if (payload.cash < 10) {
        return '初始资金不能低于 10 USDT';
    }
    if (payload.position_amount <= 0) {
        return '单笔逐仓金额必须大于 0';
    }
    if (payload.position_amount > payload.cash) {
        return '单笔逐仓金额不能大于初始资金';
    }
    if (payload.leverage < 1 || payload.leverage > 150) {
        return '杠杆必须在 x1 到 x150 之间';
    }
    const orderCheck = getOrderCheck(payload);
    if (!orderCheck.ok) {
        return orderCheck.message;
    }
    if (payload.take_profit_amount < 0 || payload.stop_loss_amount < 0) {
        return '止盈止损不能为负数';
    }
    if (payload.take_profit_amount > payload.position_amount * payload.leverage) {
        return '止盈金额不建议大于单笔名义仓位';
    }
    if (payload.stop_loss_amount > payload.position_amount) {
        return '止损金额不能大于单笔逐仓金额';
    }
    if (payload.maker_fee < 0 || payload.taker_fee < 0 || payload.maker_fee > 0.1 || payload.taker_fee > 0.1) {
        return '手续费率必须在 0 到 0.1 之间';
    }
    if (payload.slippage_rate < 0 || payload.slippage_rate > 0.1) {
        return '滑点率必须在 0 到 0.1 之间';
    }
    if (payload.funding_rate < 0 || payload.funding_rate > 0.1) {
        return '资金费率必须在 0 到 0.1 之间';
    }
    if (payload.maintenance_margin_rate < 0 || payload.maintenance_margin_rate > 0.1) {
        return '维持保证金率必须在 0 到 0.1 之间';
    }
    return '';
}


function bindRealtimeChecks() {
    const ids = ['symbol', 'position-amount', 'leverage'];
    for (const id of ids) {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', updateOrderCheck);
            el.addEventListener('change', updateOrderCheck);
        }
    }
}


function updateOrderCheck() {
    const msg = document.getElementById('order-check-msg');
    if (!msg) return;
    const payload = collectBacktestPayload();
    const check = getOrderCheck(payload);
    msg.textContent = check.message;
    msg.className = check.ok ? 'notice-msg positive' : 'notice-msg warning';
}


function getOrderCheck(payload) {
    const minNotional = MIN_NOTIONAL_BY_SYMBOL[payload.symbol] || 5;
    const notional = payload.position_amount * payload.leverage;
    const base = payload.symbol + ' 估算最小名义仓位 ' + formatNumber(minNotional, 2) + 'U，当前 ' +
        formatNumber(payload.position_amount, 2) + 'U × x' + formatNumber(payload.leverage, 0) + ' = ' +
        formatNumber(notional, 2) + 'U';

    if (notional >= minNotional) {
        return { ok: true, message: base + '，可开仓' };
    }

    const suggested = LEVERAGE_OPTIONS.find(item => payload.position_amount * item >= minNotional);
    if (suggested) {
        return {
            ok: false,
            message: base + '，实盘可能无法开仓；建议至少 x' + suggested + '，或提高逐仓金额/换交易对',
        };
    }
    return {
        ok: false,
        message: base + '，实盘可能无法开仓；当前逐仓金额过小，x150 也不够最小名义仓位',
    };
}


function collectBacktestPayload() {
    return {
        symbol: document.getElementById('symbol').value,
        timeframe: document.getElementById('timeframe').value,
        context_timeframe: document.getElementById('context-timeframe').value,
        strategy: document.getElementById('strategy').value,
        backtest_days: numberValue('backtest-days', 30),
        lookback: numberValue('lookback', 20),
        cash: numberValue('cash', 1000),
        position_amount: numberValue('position-amount', 3.3),
        leverage: numberValue('leverage', 5),
        take_profit_amount: numberValue('take-profit-amount', 1),
        stop_loss_amount: numberValue('stop-loss-amount', 2),
        maker_fee: numberValue('maker-fee', 0.0002),
        taker_fee: numberValue('taker-fee', 0.0005),
        slippage_rate: numberValue('slippage-rate', 0.0002),
        funding_rate: numberValue('funding-rate', 0.0001),
        maintenance_margin_rate: numberValue('maintenance-margin-rate', 0.005),
    };
}


function numberValue(id, fallback) {
    const value = parseFloat(document.getElementById(id).value);
    return Number.isFinite(value) ? value : fallback;
}


function updateStrategyDescription() {
    const select = document.getElementById('strategy');
    const note = document.getElementById('strategy-desc');
    const option = select.options[select.selectedIndex];
    note.textContent = option ? option.dataset.desc || '' : '';
}


async function optimizeParams() {
    const btn = document.getElementById('optimize-btn');
    const status = document.getElementById('status');
    const results = document.getElementById('results');
    const payload = collectBacktestPayload();
    const validationError = validateBacktestPayload(payload);
    if (validationError) {
        showError(validationError);
        return;
    }

    btn.disabled = true;
    status.innerHTML = '<span class="spinner"></span>正在搜索策略和参数...';
    results.classList.remove('hidden');

    try {
        const resp = await fetch('/api/optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) {
            showError(data.error || formatApiError(data));
            return;
        }
        renderOptimizationTable(data.candidates);
        status.textContent = '✅ 参数搜索完成';
        results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
        showError('运行错误: ' + err.message);
    } finally {
        btn.disabled = false;
    }
}


// ============================================================
// 数据管理
// ============================================================

async function loadDataStatus(successMessage) {
    const statusText = document.getElementById('data-status-text');
    const refreshBtn = document.getElementById('refresh-data-btn');

    refreshBtn.disabled = true;
    statusText.innerHTML = '<span class="spinner"></span>正在读取数据状态...';

    try {
        const resp = await fetch('/api/data-status');
        const data = await resp.json();
        renderDataStatusTable(data);
        statusText.textContent = successMessage || '数据状态已更新';
    } catch (err) {
        statusText.textContent = '数据状态读取失败: ' + err.message;
        renderDataStatusTable([]);
    } finally {
        refreshBtn.disabled = false;
    }
}


async function fetchSelectedData() {
    const btn = document.getElementById('fetch-data-btn');
    const statusText = document.getElementById('data-status-text');
    const symbol = document.getElementById('symbol').value;
    const days = parseInt(document.getElementById('fetch-days').value) || 365;
    const timeframes = Array.from(new Set([
        document.getElementById('context-timeframe').value,
        document.getElementById('timeframe').value,
    ]));

    btn.disabled = true;
    statusText.innerHTML = '<span class="spinner"></span>正在拉取 ' + symbol + ' ' + timeframes.join(' + ') + '...';

    try {
        const saved = [];
        for (const timeframe of timeframes) {
            const resp = await fetch('/api/fetch-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol, timeframe, days }),
            });
            const data = await resp.json();

            if (!data.success) {
                statusText.textContent = data.error || '数据拉取失败';
                return;
            }
            const rows = data.rows == null ? '--' : data.rows.toLocaleString();
            saved.push(data.timeframe + ' ' + rows + ' 行');
        }

        await loadDataStatus('已保存 ' + symbol + '：' + saved.join('，'));
    } catch (err) {
        statusText.textContent = '数据拉取失败: ' + err.message;
    } finally {
        btn.disabled = false;
    }
}


function renderDataStatusTable(items) {
    const tbody = document.getElementById('data-status-tbody');
    tbody.innerHTML = '';

    if (!items || items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">暂无数据状态</td></tr>';
        return;
    }

    for (const item of items) {
        const row = document.createElement('tr');
        const statusClass = item.exists ? 'positive' : 'negative';
        const statusText = item.exists ? '已存在' : '缺失';
        const rows = item.rows == null ? '--' : item.rows.toLocaleString();
        const size = item.file_size_kb == null ? '--' : item.file_size_kb.toFixed(1) + ' KB';

        row.innerHTML =
            '<td>' + item.symbol + '</td>' +
            '<td>' + item.timeframe + '</td>' +
            '<td class="' + statusClass + '">' + statusText + '</td>' +
            '<td>' + rows + '</td>' +
            '<td>' + size + '</td>';
        tbody.appendChild(row);
    }
}


// ============================================================
// 展示结果
// ============================================================

function displayResults(data) {
    const results = document.getElementById('results');
    results.classList.remove('hidden');

    // 指标卡片
    setMetric('metric-return', data.total_return_pct, '%', true);
    setMetric('metric-winrate', data.win_rate_pct, '%');
    setMetric('metric-drawdown', data.max_drawdown_pct, '%', true);
    setMetric('metric-sharpe', data.sharpe_ratio, '', false, 2);
    setMetric('metric-trades', data.num_trades, '次', false, 0);

    // 权益曲线图
    if (data.equity_curve && data.equity_curve.length > 0) {
        drawEquityChart(data.equity_curve);
    }

    // 交易明细表
    renderTradesTable(data.trade_list);
    renderOptimizationTable([]);

    // 滚动到结果
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}


function setMetric(id, value, suffix, colored, decimals) {
    decimals = decimals ?? 2;
    const el = document.getElementById(id);
    el.className = 'metric-value';

    if (value == null || isNaN(value)) {
        el.textContent = 'N/A';
        el.classList.add('neutral');
        return;
    }

    el.textContent = value.toFixed(decimals) + suffix;

    if (colored) {
        if (value > 0) el.classList.add('positive');
        else if (value < 0) el.classList.add('negative');
        else el.classList.add('neutral');
    }
}


// ============================================================
// 权益曲线图
// ============================================================

function drawEquityChart(equityCurve) {
    const ctx = document.getElementById('equity-chart').getContext('2d');

    if (equityChart) {
        equityChart.destroy();
    }

    // 过滤有效数据点
    const validPoints = equityCurve.filter(p => p.timestamp && p.equity != null);
    if (validPoints.length === 0) return;

    const labels = validPoints.map(p => formatChartLabel(p.timestamp));
    const equity = validPoints.map(p => p.equity);
    const initial = equity[0] || 1;

    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '权益曲线',
                data: equity,
                borderColor: '#58a6ff',
                backgroundColor: 'rgba(88, 166, 255, 0.05)',
                borderWidth: 1.5,
                fill: true,
                pointRadius: 0,
                tension: 0.1,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const pct = ((ctx.parsed.y - initial) / initial * 100).toFixed(2);
                            return ctx.parsed.y.toLocaleString() + ' USDT (' + pct + '%)';
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: { color: '#8b949e', maxTicksLimit: 15 },
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: {
                        color: '#8b949e',
                        callback: v => (v / 1000).toFixed(0) + 'k',
                    },
                },
            },
        },
    });
}


// ============================================================
// 交易明细表
// ============================================================

function renderTradesTable(trades) {
    const tbody = document.getElementById('trades-tbody');
    tbody.innerHTML = '';

    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" class="empty-cell">无交易记录</td></tr>';
        return;
    }

    const recentTrades = trades.slice(-50); // 最多显示最近 50 笔

    for (const t of recentTrades) {
        const row = document.createElement('tr');
        const pnlClass = t.pnl >= 0 ? 'positive' : 'negative';
        const pnlPctClass = t.pnl_pct >= 0 ? 'positive' : 'negative';
        const sideText = t.side === 'short' ? '做空' : '做多';
        const sideClass = t.side === 'short' ? 'negative' : 'positive';

        row.innerHTML =
            '<td class="' + sideClass + '">' + sideText + '</td>' +
            '<td>' + formatTime(t.entry_time) + '</td>' +
            '<td>' + formatTime(t.exit_time) + '</td>' +
            '<td>' + formatNumber(t.entry_price, 2) + '</td>' +
            '<td>' + formatNumber(t.exit_price, 2) + '</td>' +
            '<td>' + formatNumber(t.margin_amount, 2) + '</td>' +
            '<td>' + formatNumber(t.notional_amount, 2) + '</td>' +
            '<td>' + formatNumber(t.liquidation_price, 2) + '</td>' +
            '<td>' + formatNumber(t.funding_fee, 4) + '</td>' +
            '<td class="' + pnlClass + '">' + t.pnl.toFixed(2) + '</td>' +
            '<td class="' + pnlPctClass + '">' + t.pnl_pct.toFixed(2) + '%</td>' +
            '<td>' + (t.exit_reason || '策略平仓') + '</td>';

        tbody.appendChild(row);
    }
}


// ============================================================
// 参数搜索
// ============================================================

function renderOptimizationTable(candidates) {
    const tbody = document.getElementById('optimization-tbody');
    if (!tbody) return;
    optimizationCandidates = candidates || [];
    tbody.innerHTML = '';

    if (!candidates || candidates.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" class="empty-cell">尚未搜索</td></tr>';
        return;
    }

    for (const [index, item] of candidates.entries()) {
        const row = document.createElement('tr');
        const returnClass = item.total_return_pct >= 0 ? 'positive' : 'negative';
        const drawdownClass = item.max_drawdown_pct >= 0 ? 'positive' : 'negative';
        row.innerHTML =
            '<td>' + item.rank + '</td>' +
            '<td>' + (item.strategy_label || item.strategy || '--') + '</td>' +
            '<td>' + item.lookback + '</td>' +
            '<td>x' + formatNumber(item.leverage, 0) + '</td>' +
            '<td>' + formatNumber(item.take_profit_amount, 2) + '</td>' +
            '<td>' + formatNumber(item.stop_loss_amount, 2) + '</td>' +
            '<td class="' + returnClass + '">' + formatNumber(item.total_return_pct, 2) + '</td>' +
            '<td class="' + drawdownClass + '">' + formatNumber(item.max_drawdown_pct, 2) + '</td>' +
            '<td>' + formatNumber(item.win_rate_pct, 2) + '</td>' +
            '<td>' + item.num_trades + '</td>' +
            '<td>' + formatNumber(item.score, 2) + '</td>' +
            '<td><button class="btn-mini" onclick="applyOptimizationCandidate(' + index + ')">套用</button></td>';
        tbody.appendChild(row);
    }
}


function applyOptimizationCandidate(index) {
    const item = optimizationCandidates[index];
    if (!item) return;

    document.getElementById('strategy').value = item.strategy;
    document.getElementById('lookback').value = item.lookback;
    document.getElementById('leverage').value = String(item.leverage);
    document.getElementById('take-profit-amount').value = item.take_profit_amount;
    document.getElementById('stop-loss-amount').value = item.stop_loss_amount;
    updateStrategyDescription();
    updateOrderCheck();

    const status = document.getElementById('status');
    status.textContent = '已套用第 ' + item.rank + ' 名策略参数';
    document.querySelector('.panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}


// ============================================================
// 工具函数
// ============================================================

function formatTime(isoStr) {
    if (!isoStr) return '--';
    try {
        const d = new Date(isoStr);
        return d.toISOString().slice(0, 16).replace('T', ' ');
    } catch {
        return String(isoStr).slice(0, 16);
    }
}


function formatChartLabel(isoStr) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        const month = String(d.getUTCMonth() + 1).padStart(2, '0');
        const day = String(d.getUTCDate()).padStart(2, '0');
        const hour = String(d.getUTCHours()).padStart(2, '0');
        return month + '-' + day + ' ' + hour + ':00';
    } catch {
        return String(isoStr).slice(5, 16);
    }
}


function formatNumber(value, decimals) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '--';
    return number.toFixed(decimals);
}


function formatApiError(data) {
    if (Array.isArray(data.detail)) {
        const messages = data.detail.map(item => {
            const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : '';
            return (field ? field + ': ' : '') + item.msg;
        });
        return messages.join('；') || '请求参数不正确';
    }
    if (typeof data.detail === 'string') {
        return data.detail;
    }
    return data.error || '请求失败';
}


function showError(msg) {
    const errorMsg = document.getElementById('error-msg');
    const status = document.getElementById('status');

    errorMsg.textContent = '❌ ' + msg;
    errorMsg.classList.remove('hidden');
    status.textContent = '回测失败';
    errorMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
