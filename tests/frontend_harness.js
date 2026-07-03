'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');


class Element {
    constructor(value = '') {
        this.value = value;
        this.textContent = '';
        this.innerHTML = '';
        this.disabled = false;
        this.children = [];
        this.dataset = {};
        this.options = [{ dataset: { desc: 'mode description' } }];
        this.selectedIndex = 0;
        this.classList = {
            add() {},
            remove() {},
        };
    }

    addEventListener() {}
    appendChild(child) { this.children.push(child); }
    scrollIntoView() {}
    getContext() { return {}; }
}


function buildContext() {
    const elements = new Map();
    const requestedIds = [];
    const document = {
        getElementById(id) {
            requestedIds.push(id);
            if (!elements.has(id)) elements.set(id, new Element());
            return elements.get(id);
        },
        createElement() { return new Element(); },
        querySelector() { return new Element(); },
    };
    const window = { addEventListener() {} };
    const context = vm.createContext({
        console,
        document,
        window,
        setTimeout,
        clearTimeout,
        Chart: function Chart() {},
    });
    context.globalThis = context;
    return { context, document, elements, requestedIds };
}


function setValues(document) {
    const values = {
        symbol: 'BTC/USDT',
        timeframe: '5m',
        mode: 'RSI_REVERSAL',
        'backtest-days': '30',
        cash: '100',
        'opening-amount': '12.5',
        'margin-mode': 'CROSS',
        leverage: '5',
        'maker-fee': '0.0002',
        'taker-fee': '0.0005',
        'slippage-rate': '0.0002',
        'funding-rate': '0.0001',
        'maintenance-margin-rate': '0.005',
        'fetch-days': '30',
    };
    for (const [id, value] of Object.entries(values)) {
        document.getElementById(id).value = value;
    }
}


function trade(index) {
    return {
        strategy_source: `source-${index}`,
        mode: 'KEY_LEVEL',
        margin_mode: 'CROSS',
        environment_1h: 'BUY',
        filter_4h: 'ALLOW',
        signal_time: '2026-01-01T00:00:00Z',
        signal_price: 100,
        fill_time: '2026-01-01T00:05:00Z',
        fill_price: 101,
        atr_snapshot: 1.2345,
        stop_price: 98,
        target_price: 106,
        expected_stop_amount: 1.5,
        expected_target_amount: 2.5,
        pnl: index,
        entry_commission: 0.1,
        exit_commission: 0.2,
        funding_fee: 0.03,
    };
}


async function main() {
    const { context, document, elements, requestedIds } = buildContext();
    setValues(document);
    const scriptPath = path.join(__dirname, '..', 'static', 'js', 'backtest.js');
    vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, { filename: scriptPath });

    const api = context.__backtestTestApi;
    assert.ok(api, 'backtest.js must expose its executable test API');

    const payload = JSON.parse(JSON.stringify(api.collectBacktestPayload()));
    assert.equal(payload.mode, 'RSI_REVERSAL');
    assert.equal(payload.margin_mode, 'CROSS');
    assert.equal(payload.opening_amount, 12.5);
    for (const legacy of [
        'strategy', 'context_timeframe', 'context_lookback', 'entry_lookback',
        'position_amount', 'take_profit_amount', 'stop_loss_amount',
    ]) {
        assert.equal(Object.hasOwn(payload, legacy), false, `legacy payload field: ${legacy}`);
    }

    const feeError = api.validateBacktestPayload({
        ...payload,
        cash: 10,
        opening_amount: 10,
        leverage: 5,
        taker_fee: 0.001,
    });
    assert.match(feeError, /开仓手续费/);

    const fetchCalls = [];
    context.fetch = async (url, options = {}) => {
        fetchCalls.push({ url, options });
        if (url === '/api/data-status') {
            return { ok: true, json: async () => [] };
        }
        const body = JSON.parse(options.body);
        return {
            ok: true,
            json: async () => ({ success: true, timeframe: body.timeframe, rows: 1 }),
        };
    };
    await api.fetchSelectedData();
    const fetchedTimeframes = fetchCalls
        .filter(call => call.url === '/api/fetch-data')
        .map(call => JSON.parse(call.options.body).timeframe);
    assert.deepEqual(fetchedTimeframes, ['5m', '1h', '4h']);

    context.fetch = async () => ({
        ok: false,
        json: async () => ({ detail: '后端返回的详细错误' }),
    });
    await api.runBacktest();
    assert.match(document.getElementById('error-msg').textContent, /后端返回的详细错误/);

    vm.runInContext(`optimizationCandidates = [{
        rank: 1,
        mode: 'KEY_LEVEL_RSI',
        timeframe: '15m',
        margin_mode: 'ISOLATED',
        leverage: 20
    }]`, context);
    requestedIds.length = 0;
    api.applyOptimizationCandidate(0);
    assert.equal(document.getElementById('mode').value, 'KEY_LEVEL_RSI');
    assert.equal(document.getElementById('timeframe').value, '15m');
    assert.equal(document.getElementById('margin-mode').value, 'ISOLATED');
    assert.equal(document.getElementById('leverage').value, '20');
    for (const legacyId of [
        'strategy', 'context-timeframe', 'context-lookback', 'entry-lookback',
        'position-amount', 'take-profit-amount', 'stop-loss-amount',
    ]) {
        assert.equal(requestedIds.includes(legacyId), false, `legacy element access: ${legacyId}`);
    }

    const tbody = document.getElementById('trades-tbody');
    api.renderTradesTable(Array.from({ length: 60 }, (_, index) => trade(index)));
    assert.equal(tbody.children.length, 50);
    const rendered = tbody.children.map(row => row.innerHTML).join('\n');
    assert.doesNotMatch(rendered, /source-9</);
    assert.match(rendered, /source-10</);
    assert.match(rendered, /source-59</);
    for (const value of ['KEY_LEVEL', 'CROSS', 'BUY', 'ALLOW', '1.2345', '0.0300']) {
        assert.match(rendered, new RegExp(value));
    }
}


main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
