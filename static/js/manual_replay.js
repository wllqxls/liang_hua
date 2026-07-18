let replay = null;
let candleChart = null;
let candleSeries = null;
let candleMarkers = null;
let equityChart = null;
let equitySeries = null;
let replayLoadVersion = 0;
let lastChartViewKey = null;
let lastFocusedSignalTime = null;

const exchangeClock = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

function timeToDate(time) {
    if (typeof time === 'number') return new Date(time * 1000);
    if (typeof time === 'string') return new Date(`${time}T00:00:00Z`);
    return new Date(Date.UTC(time.year, time.month - 1, time.day));
}

function exchangeTimeParts(time) {
    return Object.fromEntries(exchangeClock.formatToParts(timeToDate(time)).map(part => [part.type, part.value]));
}

function exchangeTickFormatter(time, tickMarkType) {
    const part = exchangeTimeParts(time);
    const type = LightweightCharts.TickMarkType;
    if (tickMarkType === type.Year) return part.year;
    if (tickMarkType === type.Month) return `${part.year}-${part.month}`;
    if (tickMarkType === type.DayOfMonth) return `${part.month}-${part.day}`;
    if (tickMarkType === type.TimeWithSeconds) return `${part.hour}:${part.minute}:${part.second}`;
    return `${part.hour}:${part.minute}`;
}

function exchangeDateTime(time) {
    const part = exchangeTimeParts(time);
    return `${part.year}-${part.month}-${part.day} ${part.hour}:${part.minute}`;
}

function chart(container) {
    return LightweightCharts.createChart(container, {
        autoSize: true,
        width: container.clientWidth,
        height: container.clientHeight,
        layout: { background: { color: '#172131' }, textColor: '#cbd7e5' },
        localization: { locale: 'zh-CN', timeFormatter: exchangeDateTime },
        grid: { vertLines: { color: '#223044' }, horzLines: { color: '#223044' } },
        leftPriceScale: { visible: false },
        rightPriceScale: {
            visible: true, autoScale: true, alignLabels: true, ticksVisible: true,
            borderColor: '#38506c', scaleMargins: { top: 0.12, bottom: 0.12 },
        },
        timeScale: {
            timeVisible: true, secondsVisible: false, ticksVisible: true,
            borderColor: '#38506c', rightOffset: 8, barSpacing: 8, minBarSpacing: 3,
            lockVisibleTimeRangeOnResize: true, rightBarStaysOnScroll: true,
            tickMarkMaxCharacterLength: 8, tickMarkFormatter: exchangeTickFormatter,
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: { color: '#75869b', width: 1, labelBackgroundColor: '#334a65' },
            horzLine: { color: '#75869b', width: 1, labelBackgroundColor: '#334a65' },
        },
        handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
        handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });
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
        candleChart = chart(document.getElementById('candle-chart'));
        candleSeries = candleChart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#2ebd85', downColor: '#f6465d', borderVisible: false,
            wickUpColor: '#2ebd85', wickDownColor: '#f6465d',
        });
        candleMarkers = LightweightCharts.createSeriesMarkers(candleSeries, []);
        candleChart.subscribeCrosshairMove(param => {
            const tip = document.getElementById('chart-tooltip');
            const signal = replay?.signal_markers?.find(item => item.time === param.time);
            if (!signal || !param.point) { tip.classList.add('hidden'); return; }
            const decision = signal.decision ? ` · 人工选择：${signal.decision}` : '';
            tip.textContent = `${signal.summary}：${signal.reason}${decision}`;
            const maxLeft = Math.max(8, tip.parentElement.clientWidth - 282);
            tip.style.left = `${Math.min(param.point.x + 12, maxLeft)}px`; tip.style.top = `${Math.max(param.point.y - 55, 8)}px`; tip.classList.remove('hidden');
        });
    }
    if (!equityChart) { equityChart = chart(document.getElementById('equity-chart')); equitySeries = equityChart.addSeries(LightweightCharts.LineSeries, { color: '#21c58b', lineWidth: 2 }); }
}

function applyCandlePriceFormat(candles) {
    if (!candles.length) return;
    const price = Math.abs(candles[candles.length - 1].close);
    const precision = price >= 1000 ? 2 : price >= 100 ? 3 : price >= 1 ? 4 : price >= 0.01 ? 6 : 8;
    candleSeries.applyOptions({ priceFormat: { type: 'price', precision, minMove: 10 ** -precision } });
}

function focusLatestCandles(candles) {
    if (!candles.length) return;
    const width = document.getElementById('candle-chart').clientWidth;
    const visibleBars = Math.max(48, Math.min(140, Math.floor(width / 8)));
    candleChart.priceScale('right').applyOptions({ autoScale: true });
    candleChart.timeScale().setVisibleLogicalRange({
        from: Math.max(0, candles.length - visibleBars),
        to: candles.length - 1 + 8,
    });
}

function render(data) {
    replay = data;
    setupCharts();
    const timeframe = document.getElementById('chart-timeframe').value;
    const candles = data.charts[timeframe] || data.candles;
    const chartViewKey = `${data.session_id}:${timeframe}`;
    const shouldFocus = chartViewKey !== lastChartViewKey || (data.state === 'AWAITING_DECISION' && data.signal?.time !== lastFocusedSignalTime);
    candleSeries.setData(candles);
    applyCandlePriceFormat(candles);
    const markers = (data.signal_markers || []).map(item => {
        const side = item.side || item.suggested_side;
        return { time: item.time, position: side === 'BUY' ? 'belowBar' : 'aboveBar', color: side === 'BUY' ? '#21c58b' : '#f05d6f', shape: side === 'BUY' ? 'arrowUp' : 'arrowDown', text: item.summary };
    });
    candleMarkers.setMarkers(markers);
    equitySeries.setData(data.equity_curve.map(item => ({ time: Math.floor(new Date(item.timestamp).getTime() / 1000), value: item.equity })));
    equityChart.priceScale('right').applyOptions({ autoScale: true });
    equityChart.timeScale().fitContent();
    if (shouldFocus) focusLatestCandles(candles);
    lastChartViewKey = chartViewKey;
    if (data.state === 'AWAITING_DECISION') lastFocusedSignalTime = data.signal?.time ?? null;
    document.getElementById('chart-title').textContent = `${data.symbol} · ${timeframe} 本地回放`;
    document.getElementById('cursor-time').textContent = `${exchangeDateTime(Math.floor(new Date(data.cursor_time).getTime() / 1000))}（上海）`;
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

async function startReplay() {
    const version = ++replayLoadVersion;
    const button = document.getElementById('start-btn');
    button.disabled = true;
    button.textContent = '正在加载…';
    document.getElementById('replay-state').textContent = '载入本地数据';
    try {
        document.getElementById('error').classList.add('hidden');
        const data = await request('/api/manual-replays', payload());
        if (version !== replayLoadVersion) return;
        lastChartViewKey = null;
        lastFocusedSignalTime = null;
        render(data);
    } catch (error) {
        if (version === replayLoadVersion) {
            document.getElementById('replay-state').textContent = '加载失败';
            showError(error);
        }
    } finally {
        if (version === replayLoadVersion) {
            button.disabled = false;
            button.textContent = '开始回放';
        }
    }
}

document.getElementById('start-btn').addEventListener('click', startReplay);
document.getElementById('symbol').addEventListener('change', startReplay);
document.querySelectorAll('[data-decision]').forEach(button => button.addEventListener('click', async () => { try { render(await request(`/api/manual-replays/${replay.session_id}/decision`, { decision: button.dataset.decision })); } catch (error) { showError(error); } }));
document.getElementById('chart-timeframe').addEventListener('change', () => { if (replay) { lastChartViewKey = null; render(replay); } });
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
