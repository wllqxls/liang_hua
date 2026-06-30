/**
 * 量化回测系统 — 前端交互
 */

let equityChart = null;
let chartData = null;

window.addEventListener('DOMContentLoaded', () => {
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

    // 收集参数
    const payload = {
        symbol: document.getElementById('symbol').value,
        timeframe: document.getElementById('timeframe').value,
        strategy: document.getElementById('strategy').value,
        lookback: parseInt(document.getElementById('lookback').value) || 20,
        cash: parseFloat(document.getElementById('cash').value) || 1000000,
        commission: parseFloat(document.getElementById('commission').value) || 0.001,
    };
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
        showError('网络错误: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '▶ 开始回测';
    }
}


function validateBacktestPayload(payload) {
    if (payload.lookback < 1 || payload.lookback > 500) {
        return '回溯窗口必须在 1 到 500 之间';
    }
    if (payload.cash < 1000) {
        return '初始资金不能低于 1000 USDT';
    }
    if (payload.commission < 0 || payload.commission > 0.1) {
        return '手续费率必须在 0 到 0.1 之间';
    }
    return '';
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
    const payload = {
        symbol: document.getElementById('symbol').value,
        timeframe: document.getElementById('timeframe').value,
        days: parseInt(document.getElementById('fetch-days').value) || 365,
    };

    btn.disabled = true;
    statusText.innerHTML = '<span class="spinner"></span>正在拉取 ' + payload.symbol + ' ' + payload.timeframe + '...';

    try {
        const resp = await fetch('/api/fetch-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (!data.success) {
            statusText.textContent = data.error || '数据拉取失败';
            return;
        }

        const rows = data.rows == null ? '--' : data.rows.toLocaleString();
        await loadDataStatus('已保存 ' + data.symbol + ' ' + data.timeframe + '，共 ' + rows + ' 行');
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

    const labels = validPoints.map(p => p.timestamp);
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
                    type: 'time',
                    time: {
                        unit: 'day',
                        displayFormats: { day: 'MM-dd' },
                    },
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
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#8b949e">无交易记录</td></tr>';
        return;
    }

    const recentTrades = trades.slice(-50); // 最多显示最近 50 笔

    for (const t of recentTrades) {
        const row = document.createElement('tr');
        const pnlClass = t.pnl >= 0 ? 'positive' : 'negative';
        const pnlPctClass = t.pnl_pct >= 0 ? 'positive' : 'negative';

        row.innerHTML =
            '<td>' + formatTime(t.entry_time) + '</td>' +
            '<td>' + formatTime(t.exit_time) + '</td>' +
            '<td>' + t.entry_price.toFixed(2) + '</td>' +
            '<td>' + t.exit_price.toFixed(2) + '</td>' +
            '<td class="' + pnlClass + '">' + t.pnl.toFixed(2) + '</td>' +
            '<td class="' + pnlPctClass + '">' + t.pnl_pct.toFixed(2) + '%</td>';

        tbody.appendChild(row);
    }
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
    const results = document.getElementById('results');
    const status = document.getElementById('status');

    errorMsg.textContent = '❌ ' + msg;
    errorMsg.classList.remove('hidden');
    results.classList.remove('hidden');
    status.textContent = '回测失败';
}
