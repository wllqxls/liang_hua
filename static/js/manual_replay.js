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
let currentChartCandles = [];
let positionTimer = null;
let positionStepInFlight = false;
let orderFlowRunning = false;
let orderFlowStatusLoaded = false;
let whitelistItems = [];
let validatedStrategyProfiles = new Map();
let activeWhitelistProfile = null;
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
function payload() { return { symbol: document.getElementById('symbol').value, data_year: number('data-year'), timeframe: document.getElementById('signal-timeframe').value, mode: document.getElementById('mode').value, cash: number('cash'), opening_amount: number('opening-amount'), margin_mode: document.getElementById('margin-mode').value, leverage: number('leverage'), taker_fee: number('taker-fee'), slippage_rate: number('slippage-rate'), maintenance_margin_rate: number('maintenance-margin-rate'), liquidation_fee_rate: number('liquidation-fee-rate'), whitelist_profile: null }; }

function syncModeInputs() {
    const modeSelect = document.getElementById('mode');
    const mode = modeSelect.value;
    const strategyKey = modeSelect.selectedOptions[0]?.dataset.whitelistKey;
    const strategy = strategyKey ? validatedStrategyProfiles.get(strategyKey) : null;
    activeWhitelistProfile = strategy?.profile || null;
    const symbol = document.getElementById('symbol');
    const timeframe = document.getElementById('signal-timeframe');
    const year = document.getElementById('data-year');
    const isOrderFlow = mode === 'ORDER_FLOW_ABSORPTION_15M' || Boolean(strategy);
    const isEthRsi = mode === 'ETH_RSI_WHITELIST_5M';
    if (isOrderFlow) {
        if (strategy) symbol.value = strategy.item.symbol;
        if (!['BTC/USDT', 'ETH/USDT'].includes(symbol.value)) symbol.value = 'BTC/USDT';
        if (![2023, 2024, 2025].includes(Number(year.value))) year.value = '2025';
        timeframe.value = '15m';
    } else if (isEthRsi) {
        symbol.value = 'ETH/USDT';
        timeframe.value = '5m';
    }
    timeframe.disabled = isOrderFlow || isEthRsi;
    document.getElementById('start-btn').disabled = false;
}

async function responseJson(response) {
    const text = await response.text();
    try {
        return JSON.parse(text);
    } catch (_) {
        throw new Error(text.trim() || `服务端返回了无法识别的响应（HTTP ${response.status}）`);
    }
}

async function request(url, body) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const data = await responseJson(response);
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
            const decisionLabels = { BUY: '接受做多', SELL: '接受做空', SKIP: '放弃' };
            const decision = signal.decision ? ` · 人工选择：${decisionLabels[signal.decision] || signal.decision}` : '';
            const execution = signal.entry_status === 'INVALIDATED_AT_OPEN' ? ' · 开盘失效，未开仓' : '';
            tip.textContent = `${signal.summary}：${signal.reason}${decision}${execution}`;
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

function syncChartResetButton() {
    const table = document.querySelector('#candle-chart table');
    const priceAxisCell = table?.rows?.[0]?.cells?.[2];
    const timeAxisRow = table?.rows?.[1];
    const button = document.getElementById('chart-reset-view');
    if (!priceAxisCell || !timeAxisRow || !button) return;
    button.style.width = `${priceAxisCell.getBoundingClientRect().width}px`;
    button.style.height = `${timeAxisRow.getBoundingClientRect().height}px`;
}

function resetChartView() {
    if (!currentChartCandles.length) return;
    focusLatestCandles(currentChartCandles);
    drawingController?._scheduleRedraw();
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
    currentChartCandles = candles;
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
    document.getElementById('chart-reset-view').disabled = false;
    requestAnimationFrame(syncChartResetButton);
    if (data.state === 'POSITION_OPEN') candleChart.timeScale().scrollToPosition(8, false);
    lastChartViewKey = chartViewKey;
    if (data.state === 'AWAITING_DECISION') lastFocusedSignalTime = data.signal?.time ?? null;
    document.getElementById('chart-title').textContent = `${data.symbol} · ${timeframe} 本地回放`;
    document.getElementById('cursor-time').textContent = `${exchangeDateTime(Math.floor(new Date(data.cursor_time).getTime() / 1000))}（上海）`;
    const awaitingDecision = data.state === 'AWAITING_DECISION';
    const awaitingContinue = data.state === 'AWAITING_CONTINUE';
    document.getElementById('decision-panel').classList.toggle('hidden', !awaitingDecision && !awaitingContinue);
    const executionNotice = document.getElementById('execution-notice');
    const lastNotice = data.last_execution_notice;
    executionNotice.textContent = lastNotice ? `${lastNotice.summary}：${lastNotice.reason}` : '';
    executionNotice.classList.toggle('hidden', !lastNotice);
    document.querySelectorAll('[data-decision]').forEach(button => {
        const permitted = button.dataset.decision === 'SKIP' || button.dataset.decision === data.signal?.side;
        button.classList.toggle('hidden', !awaitingDecision || !permitted);
    });
    document.getElementById('continue-btn').classList.toggle('hidden', !awaitingContinue);
    const stateLabels = {
        AWAITING_DECISION: '等待你的决策', POSITION_OPEN: '持仓逐 K 线回放',
        AWAITING_CONTINUE: '已平仓，等待继续', FINISHED: '回放结束', RUNNING: '回放中',
    };
    document.getElementById('replay-state').textContent = stateLabels[data.state] || '回放中';
    document.getElementById('replay-state').classList.toggle('state-awaiting', awaitingDecision || awaitingContinue);
    if (data.state === 'POSITION_OPEN' && data.position_overlay?.time_exit_at) {
        document.getElementById('replay-state').textContent = `持仓逐 K 线回放 · 距时间退出 ${data.position_overlay.remaining_holding_bars} 根`;
    }
    const positionWarning = document.getElementById('position-risk-warning');
    const activeRiskWarning = data.state === 'POSITION_OPEN' ? data.position_overlay?.risk_warning : null;
    positionWarning.textContent = activeRiskWarning || '';
    positionWarning.classList.toggle('hidden', !activeRiskWarning);
    if (data.signal) {
        document.getElementById('signal-summary').textContent = data.signal.summary;
        document.getElementById('signal-reason').textContent = data.signal.reason;
        const levelText = data.signal.risk_model === 'STRUCTURAL_ZONE'
            ? `区域失效止损 ${data.signal.stop_price.toFixed(2)} · 下一关键区域止盈 ${data.signal.target_price.toFixed(2)} · 成本后预估 R:R ${data.signal.reward_risk.toFixed(2)}`
            : `参考止损 ${data.signal.stop_price.toFixed(2)} · 参考止盈 ${data.signal.target_price.toFixed(2)}`;
        document.getElementById('signal-levels').textContent = `${levelText} · ${data.signal.margin_mode_label}估算强平 ${data.signal.estimated_liquidation_price.toFixed(2)}`;
        const signalWarning = document.getElementById('signal-risk-warning');
        signalWarning.textContent = data.signal.risk_warning || '';
        signalWarning.classList.toggle('hidden', !data.signal.risk_warning);
    } else if (awaitingContinue && data.trades.length) {
        const trade = data.trades[data.trades.length - 1];
        const exitLabels = { TARGET: '本笔已止盈', STOP: '本笔已止损', LIQUIDATION: '本笔已强平', TIME: '本笔已按白名单窗口退出', FINALIZE: '本笔已按期末价格平仓' };
        document.getElementById('signal-summary').textContent = exitLabels[trade.exit_reason] || '本笔已平仓';
        document.getElementById('signal-reason').textContent = `本笔盈亏 ${trade.pnl.toFixed(2)} · 资金费收支 ${trade.funding >= 0 ? '+' : ''}${trade.funding.toFixed(4)} · 当前权益 ${trade.equity.toFixed(2)}`;
        document.getElementById('signal-levels').textContent = '点击继续，快速寻找下一个候选信号。';
        document.getElementById('signal-risk-warning').classList.add('hidden');
    }
    const rows = data.trades.map(item => `<tr><td>${item.side === 'BUY' ? '多' : '空'}</td><td>${item.fill_price.toFixed(2)}</td><td>${item.exit_price.toFixed(2)}</td><td>${item.exit_reason_label}</td><td>${item.funding >= 0 ? '+' : ''}${item.funding.toFixed(4)}</td><td>${item.pnl.toFixed(2)}</td><td>${item.equity.toFixed(2)}</td></tr>`).join('');
    document.getElementById('trade-table').innerHTML = rows || '<tr><td colspan="7">尚未接受任何交易</td></tr>';
    renderReplayStats(data.replay_stats);
    document.getElementById('cost-model-note').textContent = data.funding_available
        ? '手续费、滑点、维持保证金、强平费和本地历史资金费率均已生效。资金费以最近已收盘 5m 价格代替历史标记价格，强平使用普通 K 线，因此两者均为估算。'
        : '手续费、滑点、维持保证金和强平费已生效；当前币种/年份缺少本地资金费率，资金费未计入。强平使用普通 K 线，因此强平价为估算。';
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

function renderReplayStats(stats) {
    if (!stats) return;
    const total = stats.total_candidates == null ? '—' : stats.total_candidates;
    document.getElementById('stat-progress').textContent = `${stats.tested}/${total}`;
    document.getElementById('stat-opened').textContent = stats.opened;
    document.getElementById('stat-skipped').textContent = stats.skipped;
    document.getElementById('stat-invalidated').textContent = stats.invalidated;
    document.getElementById('stat-win-loss').textContent = `${stats.wins}/${stats.losses}`;
    document.getElementById('stat-win-rate').textContent = stats.win_rate == null ? '—' : `${(stats.win_rate * 100).toFixed(1)}%`;
    document.getElementById('stat-pnl').textContent = `${stats.cumulative_net_pnl >= 0 ? '+' : ''}${stats.cumulative_net_pnl.toFixed(2)}`;
    document.getElementById('stat-equity').textContent = stats.current_equity.toFixed(2);
}

async function startReplay() {
    syncModeInputs();
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
document.getElementById('symbol').addEventListener('change', () => {
    if (document.getElementById('mode').selectedOptions[0]?.dataset.whitelistKey) {
        document.getElementById('mode').value = 'ORDER_FLOW_ABSORPTION_15M';
    }
    syncModeInputs();
});
document.getElementById('mode').addEventListener('change', syncModeInputs);
document.querySelectorAll('[data-decision]').forEach(button => button.addEventListener('click', async () => { try { render(await request(`/api/manual-replays/${replay.session_id}/decision`, { decision: button.dataset.decision })); } catch (error) { showError(error); } }));
document.getElementById('continue-btn').addEventListener('click', continueReplay);
document.getElementById('chart-timeframe').addEventListener('change', () => { if (replay) { lastChartViewKey = null; render(replay); } });
document.getElementById('chart-reset-view').addEventListener('click', resetChartView);
new ResizeObserver(syncChartResetButton).observe(document.getElementById('candle-chart'));

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
        const correctSource = complete && ['5m', '15m', '1h', '4h'].every(timeframe => periods.get(timeframe)?.source === 'BINANCE_UM_FUTURES_ARCHIVE');
        const label = !complete ? '不完整' : correctSource ? '完整（USD-M 永续）' : '旧来源待重拉';
        return `<tr><td>${escapeHtml(symbol)}</td>${cells}<td class="${correctSource ? 'data-present' : 'data-missing'}">${label}</td></tr>`;
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
        const data = await responseJson(response);
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
    status.textContent = `正在下载并校验 ${symbol} ${year} 年 USD-M 永续归档…`;
    try {
        const response = await fetch('/api/fetch-data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol, year }) });
        const data = await responseJson(response);
        if (!response.ok || !data.success) throw new Error(data.error || data.detail || '拉取失败');
        const saved = (data.items || []).map(item => `${item.timeframe} ${Number(item.rows || 0).toLocaleString('zh-CN')} 行`).join('，');
        await loadLocalDataStatus(`已保存 ${symbol} ${year} 年：${saved}`);
    } catch (error) {
        status.textContent = `拉取失败：${error.message}`;
    } finally {
        button.disabled = false;
    }
}

function showLocalDataPage(page) {
    const isOrderFlow = page === 'orderflow';
    document.getElementById('market-data-page').classList.toggle('hidden', isOrderFlow);
    document.getElementById('order-flow-data-page').classList.toggle('hidden', !isOrderFlow);
    document.getElementById('market-data-page').setAttribute('aria-hidden', String(isOrderFlow));
    document.getElementById('order-flow-data-page').setAttribute('aria-hidden', String(!isOrderFlow));
    document.getElementById('market-data-tab').classList.toggle('active', !isOrderFlow);
    document.getElementById('order-flow-data-tab').classList.toggle('active', isOrderFlow);
    document.getElementById('market-data-tab').setAttribute('aria-selected', String(!isOrderFlow));
    document.getElementById('order-flow-data-tab').setAttribute('aria-selected', String(isOrderFlow));
    document.getElementById('local-data-panel').dataset.activeDataPage = isOrderFlow ? 'orderflow' : 'market';
    if (isOrderFlow && !orderFlowStatusLoaded) loadOrderFlowStatus();
    if (!isOrderFlow) loadLocalDataStatus();
}

function formatOrderFlowSize(kilobytes) {
    if (kilobytes == null || !Number.isFinite(Number(kilobytes))) return '--';
    const value = Number(kilobytes);
    return value >= 1024 ? `${(value / 1024).toFixed(1)} MB` : `${value.toFixed(1)} KB`;
}

function renderOrderFlowStatus(items) {
    const labels = {
        complete: '完整', usable: '可研究（OI 有缺口）', partial: '不完整',
        missing: '未下载', invalid: '审计失败',
    };
    const rows = (items || []).map(item => {
        const usable = item.state === 'complete' || item.state === 'usable';
        const annualRows = item.rows == null ? '--' : `${Number(item.rows).toLocaleString('zh-CN')} / ${Number(item.expected_rows).toLocaleString('zh-CN')}`;
        const klineMissing = item.missing_rows == null ? '--' : Number(item.missing_rows).toLocaleString('zh-CN');
        const metricsMissing = item.metrics_missing_rows == null ? '--' : `${Number(item.metrics_missing_rows).toLocaleString('zh-CN')}（${Number(item.metrics_coverage_pct || 0).toFixed(2)}% 覆盖）`;
        const funding = item.funding_rows == null ? '--' : `${Number(item.funding_rows).toLocaleString('zh-CN')} 条`;
        return `<tr><td>${escapeHtml(item.symbol || '--')}</td><td>${annualRows}</td><td class="${item.missing_rows === 0 ? 'data-present' : 'data-missing'}">${klineMissing}</td><td class="${item.metrics_missing_rows === 0 ? 'data-present' : 'data-missing'}">${metricsMissing}</td><td>${funding}</td><td>${formatOrderFlowSize(item.file_size_kb)}</td><td class="${usable ? 'data-present' : 'data-missing'}">${escapeHtml(labels[item.state] || item.state || '--')}</td></tr>`;
    }).join('');
    document.getElementById('order-flow-status-table').innerHTML = rows || '<tr><td colspan="7">暂无增强年度数据</td></tr>';
}

async function loadOrderFlowStatus(successMessage = '') {
    const year = number('data-fetch-year');
    const status = document.getElementById('order-flow-status-text');
    const button = document.getElementById('order-flow-refresh-btn');
    if (!Number.isInteger(year) || year < 2017 || year > 2100) {
        status.textContent = '请输入 2017–2100 之间的年份';
        return;
    }
    button.disabled = true;
    status.textContent = `正在读取 ${year} 年增强数据状态…`;
    try {
        const response = await fetch(`/api/order-flow/status?year=${encodeURIComponent(year)}`);
        const data = await responseJson(response);
        if (!response.ok) throw new Error(data.detail || '读取失败');
        renderOrderFlowStatus(data);
        orderFlowStatusLoaded = true;
        status.textContent = successMessage || (year === 2026 ? '2026 是未使用保留期，当前不开放拉取' : `${year} 年增强数据状态已更新`);
    } catch (error) {
        status.textContent = `增强数据状态读取失败：${error.message}`;
        renderOrderFlowStatus([]);
    } finally {
        if (!orderFlowRunning) button.disabled = false;
    }
}

async function fetchOrderFlowYear() {
    if (orderFlowRunning) return;
    const year = number('data-fetch-year');
    const yearInput = document.getElementById('data-fetch-year');
    const fetchButton = document.getElementById('order-flow-fetch-btn');
    const refreshButton = document.getElementById('order-flow-refresh-btn');
    const status = document.getElementById('order-flow-status-text');
    const progressWrap = document.getElementById('order-flow-progress-wrap');
    const progress = document.getElementById('order-flow-progress');
    const progressText = document.getElementById('order-flow-progress-text');
    if (![2023, 2024, 2025].includes(year)) {
        status.textContent = year === 2026 ? '2026 尚未结束，当前禁止拉取年度包' : '增强订单流数据只开放 2023/2024/2025';
        return;
    }
    orderFlowRunning = true;
    fetchButton.disabled = true;
    refreshButton.disabled = true;
    yearInput.disabled = true;
    progress.value = 0;
    progress.max = 1;
    progressWrap.classList.remove('hidden');
    progressText.textContent = '准备年度归档…';
    status.textContent = '后台拉取中；关闭本地数据面板不会中断任务';
    try {
        const createdResponse = await fetch('/api/order-flow/jobs', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ year }),
        });
        const created = await responseJson(createdResponse);
        if (!createdResponse.ok || !created.success || !created.job_id) throw new Error(created.detail || created.error || '任务启动失败');
        while (true) {
            const jobResponse = await fetch(`/api/order-flow/jobs/${created.job_id}`);
            const job = await responseJson(jobResponse);
            if (!jobResponse.ok) throw new Error(job.detail || '任务状态读取失败');
            const completed = Number(job.completed_count || 0);
            const total = Math.max(1, Number(job.total_count || 1));
            progress.max = total;
            progress.value = Math.min(completed, total);
            progressText.textContent = `${job.stage || '拉取中'}：${completed} / ${total}，已用 ${Number(job.elapsed_seconds || 0).toFixed(1)} 秒`;
            if (job.state === 'completed') {
                renderOrderFlowStatus(job.items || []);
                await loadOrderFlowStatus(`BTC + ETH ${year} 年增强数据已生成并完成年度审计`);
                break;
            }
            if (job.state === 'failed' || !job.success) throw new Error(job.error || '增强年度数据拉取失败');
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    } catch (error) {
        status.textContent = `增强数据拉取失败：${error.message}`;
        progressText.textContent = '任务失败，可直接重试；已校验的归档会自动跳过';
    } finally {
        orderFlowRunning = false;
        fetchButton.disabled = false;
        refreshButton.disabled = false;
        yearInput.disabled = false;
    }
}

function setLocalDataPanel(open) {
    const panel = document.getElementById('local-data-panel');
    document.getElementById('local-data-toggle').setAttribute('aria-expanded', String(open));
    panel.classList.toggle('hidden', !open);
    if (open) {
        document.getElementById('data-fetch-symbol').value = document.getElementById('symbol').value;
        document.getElementById('data-fetch-year').value = document.getElementById('data-year').value;
        const activePage = panel.dataset.activeDataPage || 'market';
        if (activePage === 'orderflow') loadOrderFlowStatus();
        else loadLocalDataStatus();
    }
}

document.getElementById('local-data-toggle').addEventListener('click', () => setLocalDataPanel(document.getElementById('local-data-panel').classList.contains('hidden')));
document.getElementById('local-data-close').addEventListener('click', () => setLocalDataPanel(false));
document.getElementById('refresh-data-btn').addEventListener('click', () => loadLocalDataStatus());
document.getElementById('fetch-data-btn').addEventListener('click', fetchLocalData);
document.getElementById('market-data-tab').addEventListener('click', () => showLocalDataPage('market'));
document.getElementById('order-flow-data-tab').addEventListener('click', () => showLocalDataPage('orderflow'));
document.getElementById('order-flow-refresh-btn').addEventListener('click', () => loadOrderFlowStatus());
document.getElementById('order-flow-fetch-btn').addEventListener('click', fetchOrderFlowYear);
document.getElementById('data-fetch-year').addEventListener('change', () => {
    orderFlowStatusLoaded = false;
    const activePage = document.getElementById('local-data-panel').dataset.activeDataPage || 'market';
    if (activePage === 'orderflow') loadOrderFlowStatus();
    else loadLocalDataStatus();
});

function whitelistKey(item) {
    return `${item.symbol}|${item.factor_id}|${item.holding_window}`;
}

function metricPercent(value, digits = 3) {
    return value == null ? '—' : `${(Number(value) * 100).toFixed(digits)}%`;
}

function winLoss(wins, losses) {
    return wins == null || losses == null ? '—' : `${wins}胜 / ${losses}败`;
}

function renderWhitelistRows() {
    const rows = whitelistItems.map((item, index) => {
        const key = whitelistKey(item);
        const strategyCreated = validatedStrategyProfiles.has(key);
        const action = `<button type="button"${strategyCreated ? ' disabled' : ' class="primary" data-create-strategy="' + index + '"'}>生成策略</button>`;
        const metricCells = [item.metrics_2023, item.metrics_2024, item.metrics_2025].map(metrics => (
            `<td>${metrics.samples}</td><td>${metricPercent(metrics.average_net_return)}</td><td>${winLoss(metrics.net_wins, metrics.net_losses)}</td>`
        )).join('');
        return `<tr><td>${escapeHtml(item.symbol.replace('/USDT', ''))}</td><td class="factor-logic">${escapeHtml(item.trigger_logic)}</td>${metricCells}<td>${action}</td></tr>`;
    }).join('');
    document.getElementById('whitelist-table').innerHTML = rows || '<tr><td colspan="12">尚未生成</td></tr>';
}

function strategyPresetName(item) {
    const symbol = item.symbol.replace('/USDT', '');
    return `[实验] 相对吸收｜${symbol}｜30日80%分位｜${item.holding_window}`;
}

function clearValidatedStrategyPresets() {
    const mode = document.getElementById('mode');
    const group = document.getElementById('validated-strategy-options');
    if (mode.selectedOptions[0]?.dataset.whitelistKey) mode.value = 'ORDER_FLOW_ABSORPTION_15M';
    group.replaceChildren();
    group.hidden = true;
    validatedStrategyProfiles = new Map();
    activeWhitelistProfile = null;
}

function createValidatedStrategyPreset(index) {
    const item = whitelistItems[index];
    const key = item ? whitelistKey(item) : '';
    if (!item) return;
    const profile = {
        factor_id: item.factor_id,
        holding_window: item.holding_window,
    };
    validatedStrategyProfiles.set(key, { item, profile });
    const group = document.getElementById('validated-strategy-options');
    const option = document.createElement('option');
    option.value = `VALIDATED_ORDER_FLOW_${index}`;
    option.textContent = strategyPresetName(item);
    option.dataset.whitelistKey = key;
    option.dataset.description = 'BTC/ETH 三年度相对吸收因子；供人工筛选实验，不代表自动盈利。';
    group.append(option);
    group.hidden = false;
    document.getElementById('symbol').value = item.symbol;
    document.getElementById('data-year').value = '2025';
    document.getElementById('mode').value = option.value;
    document.getElementById('signal-timeframe').value = '15m';
    syncModeInputs();
    renderWhitelistRows();
}

document.getElementById('whitelist-table').addEventListener('click', event => {
    const strategyButton = event.target.closest('[data-create-strategy]');
    if (strategyButton) createValidatedStrategyPreset(Number(strategyButton.dataset.createStrategy));
});

document.getElementById('whitelist-btn').addEventListener('click', async () => {
    const button = document.getElementById('whitelist-btn');
    button.disabled = true;
    button.textContent = '生成中…';
    try {
        const data = await request('/api/semi-auto-whitelist', { symbol: document.getElementById('symbol').value });
        whitelistItems = data.items;
        clearValidatedStrategyPresets();
        syncModeInputs();
        renderWhitelistRows();
    } catch (error) { showError(error); } finally {
        button.disabled = false;
        button.textContent = '生成订单流因子';
    }
});

syncModeInputs();
setupCharts();
