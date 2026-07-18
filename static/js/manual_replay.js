let replay = null;
let candleChart = null;
let candleSeries = null;
let equityChart = null;
let equitySeries = null;

function chart(container, height) {
    return LightweightCharts.createChart(container, { height, layout: { background: { color: '#172131' }, textColor: '#cbd7e5' }, grid: { vertLines: { color: '#223044' }, horzLines: { color: '#223044' } }, timeScale: { timeVisible: true } });
}

function number(id) { return Number(document.getElementById(id).value); }
function payload() { return { symbol: document.getElementById('symbol').value, data_year: number('data-year'), timeframe: document.getElementById('signal-timeframe').value, mode: document.getElementById('mode').value, cash: number('cash'), opening_amount: number('opening-amount'), leverage: number('leverage'), taker_fee: 0.0005, slippage_rate: 0.0002 }; }

async function request(url, body) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.detail || data.error || '请求失败');
    return data;
}

function setupCharts() {
    if (!candleChart) {
        candleChart = chart(document.getElementById('candle-chart'), 540); candleSeries = candleChart.addSeries(LightweightCharts.CandlestickSeries);
        candleChart.subscribeCrosshairMove(param => {
            const tip = document.getElementById('chart-tooltip');
            const signal = replay?.signal_markers?.find(item => item.time === param.time);
            if (!signal || !param.point) { tip.classList.add('hidden'); return; }
            const decision = signal.decision ? ` · 人工选择：${signal.decision}` : '';
            tip.textContent = `${signal.summary}：${signal.reason}${decision}`;
            tip.style.left = `${Math.min(param.point.x + 12, 620)}px`; tip.style.top = `${Math.max(param.point.y - 55, 8)}px`; tip.classList.remove('hidden');
        });
    }
    if (!equityChart) { equityChart = chart(document.getElementById('equity-chart'), 220); equitySeries = equityChart.addSeries(LightweightCharts.LineSeries, { color: '#21c58b', lineWidth: 2 }); }
}

function render(data) {
    replay = data;
    setupCharts();
    const timeframe = document.getElementById('chart-timeframe').value;
    const candles = data.charts[timeframe] || data.candles;
    candleSeries.setData(candles);
    const markers = (data.signal_markers || []).map(item => {
        const side = item.side || item.suggested_side;
        return { time: item.time, position: side === 'BUY' ? 'belowBar' : 'aboveBar', color: side === 'BUY' ? '#21c58b' : '#f05d6f', shape: side === 'BUY' ? 'arrowUp' : 'arrowDown', text: item.summary };
    });
    LightweightCharts.createSeriesMarkers(candleSeries, markers);
    equitySeries.setData(data.equity_curve.map(item => ({ time: Math.floor(new Date(item.timestamp).getTime() / 1000), value: item.equity })));
    document.getElementById('chart-title').textContent = `${data.symbol} · ${timeframe} 本地回放`;
    document.getElementById('cursor-time').textContent = new Date(data.cursor_time).toLocaleString();
    const awaiting = data.state === 'AWAITING_DECISION';
    document.getElementById('decision-panel').classList.toggle('hidden', !awaiting);
    document.getElementById('replay-state').textContent = awaiting ? '等待你的决策' : data.state === 'FINISHED' ? '回放结束' : '回放中';
    document.getElementById('replay-state').classList.toggle('state-awaiting', awaiting);
    if (data.signal) { document.getElementById('signal-summary').textContent = data.signal.summary; document.getElementById('signal-reason').textContent = data.signal.reason; document.getElementById('signal-levels').textContent = `参考止损 ${data.signal.stop_price.toFixed(4)} · 参考止盈 ${data.signal.target_price.toFixed(4)}`; }
    const rows = data.trades.map(item => `<tr><td>${item.side === 'BUY' ? '多' : '空'}</td><td>${item.fill_price.toFixed(4)}</td><td>${item.exit_price.toFixed(4)}</td><td>${item.exit_reason}</td><td>${item.pnl.toFixed(2)}</td><td>${item.equity.toFixed(2)}</td></tr>`).join('');
    document.getElementById('trade-table').innerHTML = rows || '<tr><td colspan="6">尚未接受任何交易</td></tr>';
    if (data.state === 'RUNNING') setTimeout(advance, 250);
}

async function advance() { if (!replay || replay.state !== 'RUNNING') return; try { render(await request(`/api/manual-replays/${replay.session_id}/advance`)); } catch (error) { showError(error); } }
function showError(error) { const el = document.getElementById('error'); el.textContent = error.message; el.classList.remove('hidden'); }

document.getElementById('start-btn').addEventListener('click', async () => {
    try {
        document.getElementById('error').classList.add('hidden');
        render(await request('/api/manual-replays', payload()));
    } catch (error) {
        showError(error);
    }
});
document.querySelectorAll('[data-decision]').forEach(button => button.addEventListener('click', async () => { try { render(await request(`/api/manual-replays/${replay.session_id}/decision`, { decision: button.dataset.decision })); } catch (error) { showError(error); } }));
document.getElementById('chart-timeframe').addEventListener('change', () => { if (replay) render(replay); });
document.getElementById('whitelist-btn').addEventListener('click', async () => {
    const button = document.getElementById('whitelist-btn'); button.disabled = true;
    document.getElementById('whitelist-status').textContent = '正在扫描 2024/2025 本地数据，请稍候…';
    try {
        const data = await request('/api/semi-auto-whitelist', { symbol: document.getElementById('symbol').value });
        const rows = data.items.map(item => `<tr><td>${item.rank}</td><td>${item.trigger_logic}</td><td>${item.timeframe}</td><td>${item.events_2024}</td><td>${item.events_2025}</td><td>${(item.gross_return_2024 * 100).toFixed(3)}%</td><td>${(item.gross_return_2025 * 100).toFixed(3)}%</td><td>${item.visual_score.toFixed(2)}</td></tr>`).join('');
        document.getElementById('whitelist-table').innerHTML = rows || '<tr><td colspan="8">没有同时满足两年毛收益与 30–100 次样本门槛的候选</td></tr>';
        document.getElementById('whitelist-status').textContent = data.items.length ? `已生成 ${data.items.length} 组；CSV 已保存到 results/semi_auto_factor_whitelist.csv` : '没有符合白名单门槛的候选。';
    } catch (error) { showError(error); } finally { button.disabled = false; }
});
