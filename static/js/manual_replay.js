let replay = null;
let candleChart = null;
let candleSeries = null;
let candleMarkers = null;
let equityChart = null;
let equitySeries = null;
let replayLoadVersion = 0;
let lastChartViewKey = null;
let lastFocusedSignalTime = null;
let renderedSignalMarkers = [];
let drawingController = null;
let positionTimer = null;
let positionStepInFlight = false;
const POSITION_STEP_DELAY_MS = 700;

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
function payload() { return { symbol: document.getElementById('symbol').value, data_year: number('data-year'), timeframe: document.getElementById('signal-timeframe').value, mode: document.getElementById('mode').value, cash: number('cash'), opening_amount: number('opening-amount'), leverage: number('leverage'), taker_fee: number('taker-fee'), slippage_rate: number('slippage-rate') }; }

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
        drawingController = new ChartDrawingController({
            overlay: document.getElementById('chart-drawing-overlay'),
            toolbar: document.getElementById('drawing-toolbar'),
            styleToolbar: document.getElementById('drawing-style-toolbar'),
            styleDragHandle: document.getElementById('drawing-style-drag'),
            chartWrap: document.querySelector('.chart-wrap'),
            chartContainer: document.getElementById('candle-chart'),
            toggle: document.getElementById('drawing-toggle'),
            colorInput: document.getElementById('draw-color'),
            widthInput: document.getElementById('draw-width'),
            styleInput: document.getElementById('draw-style'),
        });
        drawingController.attach(candleChart, candleSeries);
        candleChart.subscribeCrosshairMove(param => {
            const tip = document.getElementById('chart-tooltip');
            const signal = renderedSignalMarkers.find(item => item.displayTime === param.time);
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

function markerTimeForChart(time, timeframe) {
    const seconds = { '5m': 5 * 60, '15m': 15 * 60, '1h': 60 * 60 }[timeframe];
    return Math.floor(time / seconds) * seconds;
}

function render(data) {
    clearTimeout(positionTimer);
    replay = data;
    setupCharts();
    const chartTimeframe = document.getElementById('chart-timeframe');
    const isNewSignal = data.state === 'AWAITING_DECISION' && data.signal?.time !== lastFocusedSignalTime;
    if (isNewSignal) chartTimeframe.value = data.timeframe;
    const timeframe = chartTimeframe.value;
    const candles = data.charts[timeframe] || data.candles;
    const chartViewKey = `${data.session_id}:${timeframe}`;
    const shouldFocus = chartViewKey !== lastChartViewKey || (data.state === 'AWAITING_DECISION' && data.signal?.time !== lastFocusedSignalTime);
    candleSeries.setData(candles);
    applyCandlePriceFormat(candles);
    drawingController.setContext({ year: data.year, symbol: data.symbol, timeframe });
    drawingController.setRisk(data.position_overlay ? {
        ...data.position_overlay,
        entry_time: markerTimeForChart(data.position_overlay.entry_time, timeframe),
        end_time: markerTimeForChart(data.position_overlay.end_time, timeframe),
    } : null);
    renderedSignalMarkers = (data.signal_markers || []).map(item => ({
        ...item,
        displayTime: markerTimeForChart(item.time, timeframe),
    }));
    const markers = renderedSignalMarkers.flatMap(item => {
        const side = item.side || item.suggested_side;
        const position = side === 'BUY' ? 'belowBar' : 'aboveBar';
        const color = side === 'BUY' ? '#21c58b' : '#f05d6f';
        return [
            { time: item.displayTime, position, color, shape: 'circle', size: 0.45 },
            { time: item.displayTime, position, color, shape: side === 'BUY' ? 'arrowUp' : 'arrowDown', size: 0.85, text: side === 'BUY' ? '做多' : '做空' },
        ];
    });
    candleMarkers.setMarkers(markers);
    equitySeries.setData(data.equity_curve.map(item => ({ time: Math.floor(new Date(item.timestamp).getTime() / 1000), value: item.equity })));
    equityChart.priceScale('right').applyOptions({ autoScale: true });
    equityChart.timeScale().fitContent();
    if (shouldFocus) focusLatestCandles(candles);
    if (data.state === 'POSITION_OPEN') candleChart.timeScale().scrollToPosition(8, false);
    lastChartViewKey = chartViewKey;
    if (data.state === 'AWAITING_DECISION') lastFocusedSignalTime = data.signal?.time ?? null;
    document.getElementById('chart-title').textContent = `${data.symbol} · ${timeframe} 本地回放`;
    document.getElementById('cursor-time').textContent = `${exchangeDateTime(Math.floor(new Date(data.cursor_time).getTime() / 1000))}（上海）`;
    const awaitingDecision = data.state === 'AWAITING_DECISION';
    const awaitingContinue = data.state === 'AWAITING_CONTINUE';
    document.getElementById('decision-panel').classList.toggle('hidden', !awaitingDecision && !awaitingContinue);
    document.querySelectorAll('[data-decision]').forEach(button => button.classList.toggle('hidden', !awaitingDecision));
    document.getElementById('continue-btn').classList.toggle('hidden', !awaitingContinue);
    const stateLabels = {
        AWAITING_DECISION: '等待你的决策', POSITION_OPEN: '持仓逐 K 线回放',
        AWAITING_CONTINUE: '已平仓，等待继续', FINISHED: '回放结束', RUNNING: '回放中',
    };
    document.getElementById('replay-state').textContent = stateLabels[data.state] || '回放中';
    document.getElementById('replay-state').classList.toggle('state-awaiting', awaitingDecision || awaitingContinue);
    if (data.signal) {
        document.getElementById('signal-summary').textContent = data.signal.summary;
        document.getElementById('signal-reason').textContent = data.signal.reason;
        document.getElementById('signal-levels').textContent = `参考止损 ${data.signal.stop_price.toFixed(4)} · 参考止盈 ${data.signal.target_price.toFixed(4)}`;
    } else if (awaitingContinue && data.trades.length) {
        const trade = data.trades[data.trades.length - 1];
        const exitLabels = { TARGET: '本笔已止盈', STOP: '本笔已止损', FINALIZE: '本笔已按期末价格平仓' };
        document.getElementById('signal-summary').textContent = exitLabels[trade.exit_reason] || '本笔已平仓';
        document.getElementById('signal-reason').textContent = `本笔盈亏 ${trade.pnl.toFixed(2)} · 当前权益 ${trade.equity.toFixed(2)}`;
        document.getElementById('signal-levels').textContent = '点击继续，快速寻找下一个候选信号。';
    }
    const rows = data.trades.map(item => `<tr><td>${item.side === 'BUY' ? '多' : '空'}</td><td>${item.fill_price.toFixed(4)}</td><td>${item.exit_price.toFixed(4)}</td><td>${item.exit_reason}</td><td>${item.pnl.toFixed(2)}</td><td>${item.equity.toFixed(2)}</td></tr>`).join('');
    document.getElementById('trade-table').innerHTML = rows || '<tr><td colspan="6">尚未接受任何交易</td></tr>';
    if (data.state === 'RUNNING') positionTimer = setTimeout(advance, 250);
    if (data.state === 'POSITION_OPEN') positionTimer = setTimeout(stepPosition, POSITION_STEP_DELAY_MS);
}

async function advance() {
    if (!replay || replay.state !== 'RUNNING') return;
    const sessionId = replay.session_id;
    try {
        const data = await request(`/api/manual-replays/${sessionId}/advance`);
        if (replay?.session_id === sessionId) render(data);
    } catch (error) { showError(error); }
}
async function stepPosition() {
    if (!replay || replay.state !== 'POSITION_OPEN' || positionStepInFlight) return;
    const sessionId = replay.session_id;
    positionStepInFlight = true;
    try {
        const data = await request(`/api/manual-replays/${sessionId}/step`);
        if (replay?.session_id === sessionId) render(data);
    }
    catch (error) { showError(error); }
    finally { positionStepInFlight = false; }
}
async function continueReplay() {
    if (!replay || replay.state !== 'AWAITING_CONTINUE') return;
    try { render(await request(`/api/manual-replays/${replay.session_id}/continue`)); }
    catch (error) { showError(error); }
}
function showError(error) { const el = document.getElementById('error'); el.textContent = error.message; el.classList.remove('hidden'); }

async function startReplay() {
    const version = ++replayLoadVersion;
    clearTimeout(positionTimer);
    replay = null;
    const button = document.getElementById('start-btn');
    button.disabled = true;
    button.textContent = '正在加载…';
    document.getElementById('replay-state').textContent = '回放加载中';
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
document.getElementById('continue-btn').addEventListener('click', continueReplay);
document.getElementById('chart-timeframe').addEventListener('change', () => { if (replay) { lastChartViewKey = null; render(replay); } });

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function renderLocalDataStatus(items) {
    const grouped = new Map();
    for (const item of items || []) {
        if (!grouped.has(item.symbol)) grouped.set(item.symbol, new Map());
        grouped.get(item.symbol).set(item.timeframe, item);
    }
    const rows = Array.from(grouped.entries()).map(([symbol, periods]) => {
        const cells = ['5m', '15m', '1h', '4h'].map(timeframe => {
            const item = periods.get(timeframe);
            if (!item?.exists) return '<td class="data-missing">缺失</td>';
            const count = item.rows == null ? '--' : Number(item.rows).toLocaleString('zh-CN');
            return `<td class="data-present">${count} 行</td>`;
        }).join('');
        const complete = ['5m', '15m', '1h', '4h'].every(timeframe => periods.get(timeframe)?.exists);
        return `<tr><td>${escapeHtml(symbol)}</td>${cells}<td class="${complete ? 'data-present' : 'data-missing'}">${complete ? '完整' : '不完整'}</td></tr>`;
    }).join('');
    document.getElementById('data-status-table').innerHTML = rows || '<tr><td colspan="6">暂无数据状态</td></tr>';
}

async function loadLocalDataStatus(successMessage = '') {
    const year = number('data-fetch-year');
    const status = document.getElementById('data-status-text');
    const button = document.getElementById('refresh-data-btn');
    if (!Number.isInteger(year) || year < 2017 || year > 2100) { status.textContent = '请输入 2017–2100 之间的年份'; return; }
    button.disabled = true;
    status.textContent = `正在读取 ${year} 年本地数据状态…`;
    try {
        const response = await fetch(`/api/data-status?year=${encodeURIComponent(year)}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '读取失败');
        renderLocalDataStatus(data);
        status.textContent = successMessage || `${year} 年数据状态已更新`;
    } catch (error) {
        status.textContent = `读取失败：${error.message}`;
        renderLocalDataStatus([]);
    } finally {
        button.disabled = false;
    }
}

async function fetchLocalData() {
    const symbol = document.getElementById('data-fetch-symbol').value;
    const year = number('data-fetch-year');
    const status = document.getElementById('data-status-text');
    const button = document.getElementById('fetch-data-btn');
    if (!Number.isInteger(year) || year < 2017 || year > 2100) { status.textContent = '请输入 2017–2100 之间的年份'; return; }
    button.disabled = true;
    status.textContent = `正在拉取 ${symbol} ${year} 年 5m、15m、1h、4h 数据…`;
    try {
        const response = await fetch('/api/fetch-data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol, year }) });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || data.detail || '拉取失败');
        const saved = (data.items || []).map(item => `${item.timeframe} ${Number(item.rows || 0).toLocaleString('zh-CN')} 行`).join('，');
        await loadLocalDataStatus(`已保存 ${symbol} ${year} 年：${saved}`);
    } catch (error) {
        status.textContent = `拉取失败：${error.message}`;
    } finally {
        button.disabled = false;
    }
}

function setLocalDataPanel(open) {
    const panel = document.getElementById('local-data-panel');
    document.getElementById('local-data-toggle').setAttribute('aria-expanded', String(open));
    panel.classList.toggle('hidden', !open);
    if (open) {
        document.getElementById('data-fetch-symbol').value = document.getElementById('symbol').value;
        document.getElementById('data-fetch-year').value = document.getElementById('data-year').value;
        loadLocalDataStatus();
    }
}

document.getElementById('local-data-toggle').addEventListener('click', () => setLocalDataPanel(document.getElementById('local-data-panel').classList.contains('hidden')));
document.getElementById('local-data-close').addEventListener('click', () => setLocalDataPanel(false));
document.getElementById('refresh-data-btn').addEventListener('click', () => loadLocalDataStatus());
document.getElementById('fetch-data-btn').addEventListener('click', fetchLocalData);
document.getElementById('data-fetch-year').addEventListener('change', () => loadLocalDataStatus());

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

setupCharts();
