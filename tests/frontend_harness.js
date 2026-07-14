'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SCRIPT_PATH = path.join(__dirname, '..', 'static', 'js', 'backtest.js');
const SCRIPT = fs.readFileSync(SCRIPT_PATH, 'utf8');
const KNOWN_IDS = new Set([
    'mode', 'mode-desc', 'symbol', 'timeframe', 'backtest-days', 'cash',
    'opening-amount', 'margin-mode', 'leverage', 'maker-fee', 'taker-fee',
    'slippage-rate', 'funding-rate', 'maintenance-margin-rate', 'data-symbol', 'data-year',
    'run-btn', 'optimize-btn', 'status', 'results', 'error-msg', 'order-check-msg',
    'fetch-data-btn', 'refresh-data-btn', 'data-status-text', 'data-status-tbody',
    'trades-tbody', 'optimization-tbody', 'equity-chart', 'metric-return',
    'metric-winrate', 'metric-drawdown', 'metric-sharpe', 'metric-trades',
    'metric-quality-score', 'metric-quality-label',
    'page-next-btn', 'page-prev-btn', 'backtest-page', 'diagnostics-page',
    'diagnostic-symbol', 'diagnostic-timeframe', 'diagnostic-run-btn',
    'diagnostic-refresh-btn', 'diagnostic-error', 'diagnostic-progress-wrap',
    'diagnostic-progress', 'diagnostic-status', 'diagnostics-empty',
    'diagnostics-results', 'diagnostic-latest-meta', 'diagnostic-overall-status',
    'diagnostic-passed', 'diagnostic-best-return', 'diagnostic-best-net-pnl',
    'diagnostic-total', 'diagnostic-cross-findings', 'diagnostic-summary-tbody',
    'diagnostic-detail-list',
]);


class Element {
    constructor(value = '') {
        this.value = value;
        this.textContent = '';
        this.innerHTML = '';
        this.className = '';
        this.disabled = false;
        this.children = [];
        this.dataset = {};
        this.options = [{ dataset: { desc: 'mode description' } }];
        this.selectedIndex = 0;
        this.listeners = new Map();
        this.attributes = new Map();
        this.classes = new Set();
        this.classList = {
            add: (...names) => names.forEach(name => this.classes.add(name)),
            remove: (...names) => names.forEach(name => this.classes.delete(name)),
            toggle: (name, force) => {
                if (force === true) this.classes.add(name);
                else if (force === false) this.classes.delete(name);
                else if (this.classes.has(name)) this.classes.delete(name);
                else this.classes.add(name);
            },
            contains: name => this.classes.has(name),
        };
    }

    addEventListener(type, callback) { this.listeners.set(type, callback); }
    appendChild(child) { this.children.push(child); }
    scrollIntoView() {}
    getContext() { return {}; }
    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.get(name); }
}


function response({ ok = true, status = 200, statusText = 'OK', body = '{}' } = {}) {
    return { ok, status, statusText, text: async () => body };
}


function deferred() {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
}


function buildContext(testMode = true) {
    const elements = new Map(Array.from(KNOWN_IDS, id => [id, new Element()]));
    const requestedIds = [];
    const readyCallbacks = [];
    const document = {
        body: new Element(),
        getElementById(id) {
            requestedIds.push(id);
            if (!KNOWN_IDS.has(id)) throw new Error(`unknown element id: ${id}`);
            return elements.get(id);
        },
        createElement() { return new Element(); },
        querySelector() { return new Element(); },
    };
    const window = {
        location: { hash: '' },
        history: {
            replaceState(_state, _unused, hash) { window.location.hash = hash; },
        },
        scrollTo() {},
        addEventListener(type, callback) {
            if (type === 'DOMContentLoaded') readyCallbacks.push(callback);
        },
    };
    const context = vm.createContext({
        __BACKTEST_TEST__: testMode,
        console,
        document,
        window,
        setTimeout,
        clearTimeout,
        Chart: function Chart() {},
    });
    context.globalThis = context;
    context.fetch = async () => response({ body: '[]' });
    return { context, document, elements, readyCallbacks, requestedIds };
}


function setValues(document) {
    const values = {
        symbol: 'BTC/USDT', timeframe: '5m', mode: 'RSI_REVERSAL',
        'backtest-days': '30', cash: '100', 'opening-amount': '12.5',
        'margin-mode': 'CROSS', leverage: '5', 'maker-fee': '0.0002',
        'taker-fee': '0.0005', 'slippage-rate': '0.0002',
        'funding-rate': '0.0001', 'maintenance-margin-rate': '0.005',
        'data-symbol': 'ETH/USDT', 'data-year': '2025',
        'diagnostic-symbol': 'ETH/USDT', 'diagnostic-timeframe': '5m',
    };
    for (const [id, value] of Object.entries(values)) document.getElementById(id).value = value;
}


function trade(index, source = `source-${index}`) {
    return {
        strategy_source: source, mode: 'KEY_LEVEL', margin_mode: 'CROSS',
        environment_1h: 'BUY', filter_4h: 'ALLOW',
        signal_time: '2026-01-01T00:00:00Z', signal_price: 100,
        fill_time: '2026-01-01T00:05:00Z', fill_price: 101,
        atr_snapshot: 1.2345, stop_price: 98, target_price: 106,
        expected_stop_amount: 1.5, expected_target_amount: 2.5, pnl: index,
        entry_commission: 0.1, exit_commission: 0.2, funding_fee: 0.03,
    };
}


async function assertConditionalExport() {
    const production = buildContext(false);
    vm.runInContext(SCRIPT, production.context, { filename: SCRIPT_PATH });
    assert.equal(production.context.__backtestTestApi, undefined);
}


function assertRequiredNumbers(api, document) {
    const cases = [
        ['cash', '', /账户总金额/],
        ['opening-amount', 'abc', /开仓金额/],
        ['leverage', 'Infinity', /杠杆/],
        ['maker-fee', '', /Maker 手续费率/],
    ];
    for (const [id, invalid, message] of cases) {
        const element = document.getElementById(id);
        const valid = element.value;
        element.value = invalid;
        assert.throws(() => api.collectBacktestPayload(), message);
        element.value = valid;
    }
}


async function assertSafeApiParsing(api) {
    await assert.rejects(
        api.parseApiResponse(response({ ok: false, status: 500, statusText: 'Server Error', body: '<html>bad</html>' })),
        /HTTP 500 Server Error/,
    );
    await assert.rejects(
        api.parseApiResponse(response({ ok: false, status: 502, statusText: 'Bad Gateway', body: '' })),
        /HTTP 502 Bad Gateway/,
    );
    await assert.rejects(
        api.parseApiResponse(response({ ok: false, status: 422, statusText: 'Unprocessable', body: '{"detail":"safe detail"}' })),
        /safe detail/,
    );
}


async function assertOperationController(api, context, document) {
    const backtestResponse = deferred();
    const optimizeCreateResponse = deferred();
    context.fetch = async url => {
        if (url === '/api/backtest') return backtestResponse.promise;
        if (url === '/api/optimize/jobs') return optimizeCreateResponse.promise;
        if (url === '/api/optimize/jobs/job-1') {
            return response({ body: JSON.stringify({
                success: true, state: 'completed', candidates: [], evaluated_count: 1,
                total_budget: 1, filtered_count: 1,
            }) });
        }
        throw new Error(`unexpected URL: ${url}`);
    };

    const oldRun = api.runBacktest();
    assert.equal(document.getElementById('run-btn').disabled, true);
    assert.equal(document.getElementById('optimize-btn').disabled, true);

    const currentOptimize = api.optimizeParams();
    assert.equal(document.getElementById('run-btn').disabled, true);
    assert.equal(document.getElementById('optimize-btn').disabled, true);
    const optimizeStatus = document.getElementById('status').innerHTML;

    backtestResponse.resolve(response({ body: JSON.stringify({
        success: true, total_return_pct: 99, win_rate_pct: 99,
        max_drawdown_pct: 0, sharpe_ratio: 1, num_trades: 0,
        quality_score: 1, quality_label: 'old response', quality_grade: 'watch',
        equity_curve: [], trade_list: [],
    }) }));
    await oldRun;
    assert.equal(document.getElementById('status').innerHTML, optimizeStatus);
    assert.equal(document.getElementById('run-btn').disabled, true);
    assert.equal(document.getElementById('optimize-btn').disabled, true);

    optimizeCreateResponse.resolve(response({ body: '{"success":true,"job_id":"job-1"}' }));
    await currentOptimize;
    assert.equal(document.getElementById('run-btn').disabled, false);
    assert.equal(document.getElementById('optimize-btn').disabled, false);
    assert.match(document.getElementById('status').textContent, /智能搜索完成/);
}


async function assertDiagnosticPage(api, context, document) {
    api.showAppPage('diagnostics');
    assert.equal(document.body.dataset.activePage, 'diagnostics');
    assert.equal(document.getElementById('backtest-page').getAttribute('aria-hidden'), 'true');
    assert.equal(document.getElementById('diagnostics-page').getAttribute('aria-hidden'), 'false');
    assert.equal(document.getElementById('page-next-btn').classList.contains('hidden'), true);
    assert.equal(document.getElementById('page-prev-btn').classList.contains('hidden'), false);

    api.renderDiagnostics({
        available: true,
        symbol: 'ETH/USDT',
        timeframe: '5m',
        days: 365,
        generated_at: '2026-07-14T00:00:00Z',
        passed_count: 0,
        total_count: 1,
        cross_mode_findings: ['组合模式没有形成实质性的交易筛选。'],
        summary: [{
            mode: 'KEY_LEVEL', margin_mode: 'ISOLATED', status: '未通过验证',
            annual_return_pct: -10, max_drawdown_pct: -20, annual_trades: 100,
            pre_fee_pnl: -1, commission: 5, net_pnl: -6, profit_factor: 0.5,
            findings: ['失败原因'], reasons: ['全年收益不为正'],
        }],
    });
    assert.equal(document.getElementById('diagnostic-summary-tbody').children.length, 1);
    assert.equal(document.getElementById('diagnostic-detail-list').children.length, 1);
    assert.equal(document.getElementById('diagnostic-cross-findings').children[0].textContent,
        '组合模式没有形成实质性的交易筛选。');

    context.fetch = async url => {
        if (url === '/api/diagnostics/jobs') {
            return response({ body: '{"success":true,"job_id":"diagnostic-1"}' });
        }
        if (url === '/api/diagnostics/jobs/diagnostic-1') {
            return response({ body: JSON.stringify({
                success: true, state: 'completed', stage: '完成',
                completed_count: 3, total_count: 3, elapsed_seconds: 20,
            }) });
        }
        if (url === '/api/diagnostics/latest') {
            return response({ body: JSON.stringify({
                available: true, symbol: 'ETH/USDT', timeframe: '5m', days: 365,
                passed_count: 0, total_count: 0, summary: [], cross_mode_findings: [],
            }) });
        }
        throw new Error(`unexpected URL: ${url}`);
    };
    await api.runStrategyDiagnostics();
    assert.equal(document.getElementById('diagnostic-run-btn').disabled, false);
    assert.match(document.getElementById('diagnostic-status').textContent, /诊断完成/);
}


function assertEscaping(api, document) {
    const attack = '<img src=x onerror=alert(1)>';
    api.renderOptimizationTable([], {
        evaluated_count: 1,
        filtered_count: attack,
    });
    const summaryHtml = document.getElementById('optimization-tbody').innerHTML;
    assert.doesNotMatch(summaryHtml, /<img/);

    api.renderDataStatusTable([{ symbol: attack, timeframe: attack, exists: true, rows: 1, file_size_kb: 1 }]);
    api.renderOptimizationTable([{
        rank: attack, mode_label: attack, quality_label: attack, quality_grade: attack,
        quality_reasons: [attack], timeframe: attack, margin_mode: attack, leverage: 1,
        total_return_pct: 1, out_sample_return_pct: 1, random_pass_rate_pct: 1,
        random_worst_return_pct: 1, long_window_return_pct: 1, long_window_days: attack,
        robustness_label: attack, robustness_score: 1, max_drawdown_pct: -1,
        win_rate_pct: 1, profit_factor: 1, max_consecutive_losses: attack,
        num_trades: attack, quality_score: 1,
    }]);
    const maliciousTrade = trade(1, attack);
    maliciousTrade.signal_time = attack;
    api.renderTradesTable([maliciousTrade]);
    const html = [
        ...document.getElementById('data-status-tbody').children,
        ...document.getElementById('optimization-tbody').children,
        ...document.getElementById('trades-tbody').children,
    ].map(row => row.innerHTML).join('\n');
    assert.doesNotMatch(html, /<img/);
    assert.match(html, /&lt;img/);
}


async function main() {
    await assertConditionalExport();
    const { context, document, readyCallbacks, requestedIds } = buildContext(true);
    setValues(document);
    vm.runInContext(SCRIPT, context, { filename: SCRIPT_PATH });
    const api = context.__backtestTestApi;
    assert.ok(api, 'backtest.js must expose its test API only in test mode');

    assert.equal(readyCallbacks.length, 1);
    readyCallbacks[0]();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(document.getElementById('refresh-data-btn').disabled, false);
    assert.ok(document.getElementById('mode').listeners.has('change'));
    assert.ok(document.getElementById('cash').listeners.has('input'));

    const payload = JSON.parse(JSON.stringify(api.collectBacktestPayload()));
    assert.equal(payload.mode, 'RSI_REVERSAL');
    assert.equal(payload.margin_mode, 'CROSS');
    assert.equal(payload.opening_amount, 12.5);
    assert.equal(payload.data_year, 2025);
    for (const legacy of ['strategy', 'context_timeframe', 'position_amount', 'take_profit_amount']) {
        assert.equal(Object.hasOwn(payload, legacy), false);
    }
    assertRequiredNumbers(api, document);
    await assertSafeApiParsing(api);
    await assertDiagnosticPage(api, context, document);

    const feeError = api.validateBacktestPayload({ ...payload, cash: 10, opening_amount: 10, leverage: 5, taker_fee: 0.001 });
    assert.match(feeError, /开仓手续费/);

    const fetchCalls = [];
    context.fetch = async (url, options = {}) => {
        fetchCalls.push({ url, options });
        if (url.startsWith('/api/data-status')) return response({ body: JSON.stringify([
            { symbol: 'BTC/USDT', timeframe: '5m', year: 2025, exists: true, rows: 1 },
            { symbol: 'BTC/USDT', timeframe: '15m', year: 2025, exists: false },
            { symbol: 'BTC/USDT', timeframe: '1h', year: 2025, exists: false },
            { symbol: 'BTC/USDT', timeframe: '4h', year: 2025, exists: false },
            { symbol: 'ETH/USDT', timeframe: '5m', year: 2025, exists: true, rows: 2 },
            { symbol: 'ETH/USDT', timeframe: '15m', year: 2025, exists: true, rows: 2 },
            { symbol: 'ETH/USDT', timeframe: '1h', year: 2025, exists: true, rows: 2 },
            { symbol: 'ETH/USDT', timeframe: '4h', year: 2025, exists: true, rows: 2 },
        ]) });
        const body = JSON.parse(options.body);
        return response({ body: JSON.stringify({
            success: true,
            symbol: body.symbol,
            year: body.year,
            items: [
                { symbol: body.symbol, timeframe: '5m', year: body.year, exists: true, rows: 1 },
                { symbol: body.symbol, timeframe: '15m', year: body.year, exists: true, rows: 1 },
                { symbol: body.symbol, timeframe: '1h', year: body.year, exists: true, rows: 1 },
                { symbol: body.symbol, timeframe: '4h', year: body.year, exists: true, rows: 1 },
            ],
        }) });
    };
    await api.fetchSelectedData();
    const yearlyFetches = fetchCalls.filter(call => call.url === '/api/fetch-data');
    assert.equal(yearlyFetches.length, 1);
    assert.deepEqual(JSON.parse(yearlyFetches[0].options.body), { symbol: 'ETH/USDT', year: 2025 });
    assert.equal(fetchCalls.some(call => call.url === '/api/data-status?year=2025'), true);
    const dataRows = document.getElementById('data-status-tbody').children.map(row => row.innerHTML).join('\n');
    assert.equal(dataRows.includes('BTC/USDT'), true);
    assert.equal(dataRows.includes('ETH/USDT'), true);
    assert.equal(dataRows.includes('5m / 15m / 1h / 4h'), true);
    assert.equal(dataRows.includes('5m 缺失'), false);
    assert.equal(dataRows.includes('15m 已存在'), false);

    context.fetch = async () => response({ ok: false, status: 422, statusText: 'Invalid', body: '{"detail":"backend detail"}' });
    await api.runBacktest();
    assert.match(document.getElementById('error-msg').textContent, /backend detail/);

    vm.runInContext("optimizationCandidates = [{rank:1,mode:'KEY_LEVEL_RSI',timeframe:'15m',margin_mode:'ISOLATED',leverage:20}]", context);
    requestedIds.length = 0;
    api.applyOptimizationCandidate(0);
    assert.equal(document.getElementById('mode').value, 'KEY_LEVEL_RSI');
    assert.equal(document.getElementById('timeframe').value, '15m');
    assert.equal(document.getElementById('margin-mode').value, 'ISOLATED');
    assert.equal(document.getElementById('leverage').value, '20');
    assert.equal(requestedIds.includes('strategy'), false);

    const tbody = document.getElementById('trades-tbody');
    api.renderTradesTable(Array.from({ length: 60 }, (_, index) => trade(index)));
    assert.equal(tbody.children.length, 50);
    const rendered = tbody.children.map(row => row.innerHTML).join('\n');
    assert.doesNotMatch(rendered, /source-9</);
    assert.match(rendered, /source-10</);
    assert.match(rendered, /source-59</);

    assertEscaping(api, document);
    await assertOperationController(api, context, document);
}


main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
