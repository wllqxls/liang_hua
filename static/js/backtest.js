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
    updateModeDescription();
    document.getElementById('mode').addEventListener('change', updateModeDescription);
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
    if (payload.backtest_days < 1 || payload.backtest_days > 3650) {
        return '回测天数必须在 1 到 3650 之间';
    }
    if (!['5m', '15m'].includes(payload.timeframe)) {
        return '入场周期只能选择 5m 或 15m';
    }
    if (payload.cash < 10) {
        return '初始资金不能低于 10 USDT';
    }
    if (payload.opening_amount <= 0) {
        return '开仓金额必须大于 0';
    }
    if (payload.opening_amount > payload.cash) {
        return '开仓金额不能大于账户总金额';
    }
    if (payload.leverage < 1 || payload.leverage > 150) {
        return '杠杆必须在 x1 到 x150 之间';
    }
    if (payload.maker_fee < 0 || payload.taker_fee < 0 || payload.maker_fee > 0.1 || payload.taker_fee > 0.1) {
        return '手续费率必须在 0 到 0.1 之间';
    }
    const entryFee = payload.opening_amount * payload.leverage * payload.taker_fee;
    if (payload.opening_amount + entryFee > payload.cash) {
        return '账户总金额必须覆盖开仓金额和开仓手续费';
    }
    const orderCheck = getOrderCheck(payload);
    if (!orderCheck.ok) {
        return orderCheck.message;
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


function validateOptimizationPayload(payload) {
    return validateBacktestPayload(payload);
}


function bindRealtimeChecks() {
    const ids = ['symbol', 'cash', 'opening-amount', 'leverage', 'taker-fee'];
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
    const notional = payload.opening_amount * payload.leverage;
    const base = payload.symbol + ' 估算最小名义仓位 ' + formatNumber(minNotional, 2) + 'U，当前 ' +
        formatNumber(payload.opening_amount, 2) + 'U × x' + formatNumber(payload.leverage, 0) + ' = ' +
        formatNumber(notional, 2) + 'U';

    if (notional >= minNotional) {
        return { ok: true, message: base + '，可开仓' };
    }

    const suggested = LEVERAGE_OPTIONS.find(item => payload.opening_amount * item >= minNotional);
    if (suggested) {
        return {
            ok: false,
            message: base + '，实盘可能无法开仓；建议至少 x' + suggested + '，或提高开仓金额/换交易对象',
        };
    }
    return {
        ok: false,
        message: base + '，实盘可能无法开仓；当前开仓金额过小，x150 也不够最小名义仓位',
    };
}


function collectBacktestPayload() {
    return {
        symbol: document.getElementById('symbol').value,
        timeframe: document.getElementById('timeframe').value,
        mode: document.getElementById('mode').value,
        backtest_days: numberValue('backtest-days', 30),
        cash: numberValue('cash', 100),
        opening_amount: numberValue('opening-amount', 10),
        margin_mode: document.getElementById('margin-mode').value,
        leverage: numberValue('leverage', 5),
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


function updateModeDescription() {
    const select = document.getElementById('mode');
    const note = document.getElementById('mode-desc');
    const option = select.options[select.selectedIndex];
    note.textContent = option ? option.dataset.desc || '' : '';
}


async function optimizeParams() {
    const btn = document.getElementById('optimize-btn');
    const status = document.getElementById('status');
    const results = document.getElementById('results');
    const payload = collectBacktestPayload();
    const validationError = validateOptimizationPayload(payload);
    if (validationError) {
        showError(validationError);
        return;
    }

    btn.disabled = true;
    status.innerHTML = '<span class="spinner"></span>正在搜索策略和参数...';
    results.classList.remove('hidden');

    try {
        const resp = await fetch('/api/optimize/jobs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const created = await resp.json();
        if (!resp.ok) {
            showError(formatApiError(created));
            return;
        }
        if (!created.success) {
            showError(created.error || '智能搜索启动失败');
            return;
        }
        const jobId = created.job_id;
        while (true) {
            const jobResp = await fetch('/api/optimize/jobs/' + jobId);
            const data = await jobResp.json();
            if (!jobResp.ok) {
                throw new Error(formatApiError(data));
            }
            if (!data.success) {
                throw new Error(data.error || '智能搜索失败');
            }
            const evaluated = data.evaluated_count || 0;
            const total = data.total_budget || 0;
            const percent = total > 0 ? Math.min(100, Math.round(evaluated / total * 100)) : 0;
            status.innerHTML = '<span class="spinner"></span>' + (data.stage || '搜索') +
                '：' + evaluated + ' / ' + total + '（' + percent + '%），已用 ' +
                formatDuration(data.elapsed_seconds || 0);

            if (data.state === 'completed') {
                renderOptimizationTable(data.candidates, data);
                status.textContent = '✅ 智能搜索完成，评估 ' + evaluated +
                    ' 个，通过 ' + (data.candidates || []).length + ' 个，过滤 ' +
                    (data.filtered_count || 0) + ' 个' + (data.partial ? '（达到时间预算，已提前结束）' : '');
                results.scrollIntoView({ behavior: 'smooth', block: 'start' });
                break;
            }
            if (data.state === 'failed') {
                throw new Error(data.error || '智能搜索失败');
            }
            await delay(1000);
        }
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
        if (!resp.ok) {
            throw new Error(formatApiError(data));
        }
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
    const timeframes = Array.from(
        new Set([document.getElementById('timeframe').value, '1h', '4h'])
    );

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

            if (!resp.ok || !data.success) {
                statusText.textContent = resp.ok
                    ? (data.error || '数据拉取失败')
                    : formatApiError(data);
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
    setMetric('metric-quality-score', data.quality_score, '', true, 0);
    setTextMetric('metric-quality-label', data.quality_label, data.quality_grade);

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

function formatEquityTick(value) {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) return '';

    const absoluteValue = Math.abs(numericValue);
    if (absoluteValue >= 1_000_000) {
        return (numericValue / 1_000_000).toLocaleString('zh-CN', {
            maximumFractionDigits: 1,
        }) + 'M';
    }
    if (absoluteValue >= 1_000) {
        return (numericValue / 1_000).toLocaleString('zh-CN', {
            maximumFractionDigits: 1,
        }) + 'k';
    }
    return numericValue.toLocaleString('zh-CN', {
        maximumFractionDigits: absoluteValue < 10 ? 2 : 1,
    });
}

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
                        callback: formatEquityTick,
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
        tbody.innerHTML = '<tr><td colspan="18" class="empty-cell">无交易记录</td></tr>';
        return;
    }

    const recentTrades = trades.slice(-50); // 最多显示最近 50 笔

    for (const t of recentTrades) {
        const row = document.createElement('tr');
        const pnlClass = t.pnl >= 0 ? 'positive' : 'negative';
        row.innerHTML =
            '<td>' + escapeHtml(t.strategy_source || '--') + '</td>' +
            '<td>' + escapeHtml(t.mode || '--') + '</td>' +
            '<td>' + escapeHtml(t.margin_mode || '--') + '</td>' +
            '<td>' + escapeHtml(t.environment_1h || '--') + '</td>' +
            '<td>' + escapeHtml(t.filter_4h || '--') + '</td>' +
            '<td>' + formatTime(t.signal_time) + '</td>' +
            '<td>' + formatNumber(t.signal_price, 2) + '</td>' +
            '<td>' + formatTime(t.fill_time) + '</td>' +
            '<td>' + formatNumber(t.fill_price, 2) + '</td>' +
            '<td>' + formatNumber(t.atr_snapshot, 4) + '</td>' +
            '<td>' + formatNumber(t.stop_price, 2) + '</td>' +
            '<td>' + formatNumber(t.target_price, 2) + '</td>' +
            '<td>' + formatNumber(t.expected_stop_amount, 2) + '</td>' +
            '<td>' + formatNumber(t.expected_target_amount, 2) + '</td>' +
            '<td class="' + pnlClass + '">' + formatNumber(t.pnl, 2) + '</td>' +
            '<td>' + formatNumber(t.entry_commission, 4) + '</td>' +
            '<td>' + formatNumber(t.exit_commission, 4) + '</td>' +
            '<td>' + formatNumber(t.funding_fee, 4) + '</td>';

        tbody.appendChild(row);
    }
}


// ============================================================
// 参数搜索
// ============================================================

function renderOptimizationTable(candidates, summary) {
    const tbody = document.getElementById('optimization-tbody');
    if (!tbody) return;
    optimizationCandidates = candidates || [];
    tbody.innerHTML = '';

    if (!candidates || candidates.length === 0) {
        const evaluated = summary && summary.evaluated_count ? summary.evaluated_count : 0;
        const filtered = summary && summary.filtered_count ? summary.filtered_count : 0;
        const text = evaluated > 0
            ? '没有通过严格过滤的组合，已过滤 ' + filtered + ' / ' + evaluated + ' 个'
            : '尚未搜索';
        tbody.innerHTML = '<tr><td colspan="19" class="empty-cell">' + text + '</td></tr>';
        return;
    }

    for (const [index, item] of candidates.entries()) {
        const row = document.createElement('tr');
        const returnClass = item.total_return_pct >= 0 ? 'positive' : 'negative';
        const outReturnClass = item.out_sample_return_pct >= 0 ? 'positive' : 'negative';
        const randomWorstClass = item.random_worst_return_pct >= 0 ? 'positive' : 'negative';
        const drawdownClass = item.max_drawdown_pct >= 0 ? 'positive' : 'negative';
        const badge = qualityBadge(item.quality_label, item.quality_grade, item.quality_reasons);
        const robustness = robustnessBadge(item.robustness_label, item.robustness_score);
        row.innerHTML =
            '<td>' + item.rank + '</td>' +
            '<td>' + escapeHtml(item.mode_label || item.mode || '--') + '</td>' +
            '<td>' + badge + '</td>' +
            '<td>' + (item.timeframe || '--') + '</td>' +
            '<td>' + escapeHtml(item.margin_mode || '--') + '</td>' +
            '<td>x' + formatNumber(item.leverage, 0) + '</td>' +
            '<td class="' + returnClass + '">' + formatNumber(item.total_return_pct, 2) + '</td>' +
            '<td class="' + outReturnClass + '">' + formatNumber(item.out_sample_return_pct, 2) + '</td>' +
            '<td>' + formatNumber(item.random_pass_rate_pct, 0) + '%</td>' +
            '<td class="' + randomWorstClass + '">' + formatNumber(item.random_worst_return_pct, 2) + '</td>' +
            '<td>' + formatNumber(item.long_window_return_pct, 2) +
                (item.long_window_days ? ' (' + item.long_window_days + '天)' : '') + '</td>' +
            '<td>' + robustness + '</td>' +
            '<td class="' + drawdownClass + '">' + formatNumber(item.max_drawdown_pct, 2) + '</td>' +
            '<td>' + formatNumber(item.win_rate_pct, 2) + '</td>' +
            '<td>' + formatNumber(item.profit_factor, 2) + '</td>' +
            '<td>' + item.max_consecutive_losses + '</td>' +
            '<td>' + item.num_trades + '</td>' +
            '<td>' + formatNumber(item.quality_score, 0) + '</td>' +
            '<td><button class="btn-mini" onclick="applyOptimizationCandidate(' + index + ')">套用</button></td>';
        tbody.appendChild(row);
    }
}


function applyOptimizationCandidate(index) {
    const item = optimizationCandidates[index];
    if (!item) return;

    document.getElementById('mode').value = item.mode;
    document.getElementById('timeframe').value = item.timeframe;
    document.getElementById('margin-mode').value = item.margin_mode;
    document.getElementById('leverage').value = String(item.leverage);
    updateModeDescription();
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


function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}


function formatDuration(seconds) {
    const value = Math.max(0, Math.round(seconds));
    const minutes = Math.floor(value / 60);
    const remaining = value % 60;
    return minutes > 0 ? minutes + '分' + remaining + '秒' : remaining + '秒';
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


function setTextMetric(id, text, grade) {
    const el = document.getElementById(id);
    el.className = 'metric-value';
    el.textContent = text || '--';
    if (grade === 'recommend') el.classList.add('positive');
    else if (grade === 'reject') el.classList.add('negative');
    else el.classList.add('neutral');
}


function qualityBadge(label, grade, reasons) {
    const safeLabel = escapeHtml(label || '--');
    const title = Array.isArray(reasons) ? escapeHtml(reasons.join('；')) : '';
    return '<span class="quality-badge ' + escapeHtml(grade || 'watch') + '" title="' + title + '">' +
        safeLabel + '</span>';
}


function robustnessBadge(label, score) {
    let grade = 'reject';
    if (label === '稳健') grade = 'recommend';
    else if (label === '观察') grade = 'watch';
    return '<span class="quality-badge ' + grade + '" title="稳健分 ' + formatNumber(score, 0) + '">' +
        escapeHtml(label || '未验证') + '</span>';
}


function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
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
