from pathlib import Path


ROOT = Path(__file__).parents[1]
STYLE_PATH = ROOT / 'static' / 'css' / 'style.css'
SCRIPT_PATH = ROOT / 'static' / 'js' / 'backtest.js'
TEMPLATE_PATH = ROOT / 'templates' / 'backtest.html'


def _sources() -> tuple[str, str, str]:
    return (
        TEMPLATE_PATH.read_text(encoding='utf-8'),
        SCRIPT_PATH.read_text(encoding='utf-8'),
        STYLE_PATH.read_text(encoding='utf-8'),
    )


def test_control_contract_uses_signal_and_margin_modes_in_required_order() -> None:
    template, _, _ = _sources()

    assert '{% for mode in modes %}' in template
    assert 'id="mode"' in template
    assert 'id="timeframe"' in template
    assert template.index('id="symbol"') < template.index('id="mode"')
    assert template.index('id="mode"') < template.index('id="timeframe"')
    assert template.index('id="timeframe"') < template.index('id="backtest-days"')
    assert template.index('id="backtest-days"') < template.index('id="leverage"')
    timeframe = template.split('id="timeframe"', 1)[1].split('</select>', 1)[0]
    assert 'value="5m"' in timeframe
    assert 'value="15m"' in timeframe
    assert 'value="1h"' not in timeframe

    funds = template.split('<div class="funds-grid">', 1)[1].split('<details class="advanced-options">', 1)[0]
    assert funds.index('id="cash"') < funds.index('id="margin-mode"') < funds.index('id="opening-amount"')
    assert '<option value="ISOLATED" selected>逐仓</option>' in funds
    assert '<option value="CROSS">全仓</option>' in funds


def test_legacy_controls_and_javascript_are_removed() -> None:
    template, script, _ = _sources()
    combined = template + script

    for legacy in (
        'context-timeframe', 'context-lookback', 'entry-lookback',
        'position-amount', 'take-profit-amount', 'stop-loss-amount',
    ):
        assert legacy not in combined
    assert "getElementById('strategy')" not in script
    assert 'item.strategy' not in script
    assert 'context_timeframe' not in script
    assert 'context_lookback' not in script
    assert 'entry_lookback' not in script
    assert 'position_amount' not in script
    assert 'take_profit_amount' not in script
    assert 'stop_loss_amount' not in script


def test_payload_and_validation_match_new_backtest_api() -> None:
    _, script, _ = _sources()

    assert "mode: document.getElementById('mode').value" in script
    assert "timeframe: document.getElementById('timeframe').value" in script
    assert "margin_mode: document.getElementById('margin-mode').value" in script
    assert "opening_amount: numberValue('opening-amount', 10)" in script
    assert "['5m', '15m'].includes(payload.timeframe)" in script
    assert 'payload.opening_amount + entryFee > payload.cash' in script
    assert 'payload.opening_amount * payload.leverage * payload.taker_fee' in script


def test_data_fetch_requests_entry_one_hour_and_four_hour_once() -> None:
    _, script, _ = _sources()

    assert "new Set([document.getElementById('timeframe').value, '1h', '4h'])" in script
    assert "if (!resp.ok || !data.success)" in script
    assert 'formatApiError(data)' in script


def test_optimization_table_and_apply_use_only_new_configuration_fields() -> None:
    template, script, _ = _sources()
    table = template.split('id="optimization-table"', 1)[1].split('</table>', 1)[0]
    renderer = script.split('function renderOptimizationTable', 1)[1]
    renderer = renderer.split('function applyOptimizationCandidate', 1)[0]
    apply = script.split('function applyOptimizationCandidate', 1)[1].split('// 工具函数', 1)[0]

    for heading in ('信号模式', '入场周期', '保证金模式', '杠杆'):
        assert f'<th>{heading}</th>' in table
    for old_heading in ('策略', '环境周期', '环境回溯', '入场回溯', '止盈U', '止损U'):
        assert f'<th>{old_heading}</th>' not in table
    assert 'item.mode_label || item.mode' in renderer
    assert 'item.margin_mode' in renderer
    assert "document.getElementById('mode').value = item.mode" in apply
    assert "document.getElementById('timeframe').value = item.timeframe" in apply
    assert "document.getElementById('margin-mode').value = item.margin_mode" in apply
    assert "document.getElementById('leverage').value = String(item.leverage)" in apply
    for legacy in ('strategy', 'context', 'lookback', 'take_profit', 'stop_loss'):
        assert legacy not in renderer
        assert legacy not in apply


def test_trade_table_uses_signal_audit_fields_and_limits_rows() -> None:
    template, script, _ = _sources()
    table = template.split('id="trades-table"', 1)[1].split('</table>', 1)[0]
    renderer = script.split('function renderTradesTable', 1)[1].split('// 参数搜索', 1)[0]
    expected_fields = (
        'strategy_source', 'mode', 'margin_mode', 'environment_1h', 'filter_4h',
        'signal_time', 'signal_price', 'fill_time', 'fill_price', 'atr_snapshot',
        'stop_price', 'target_price', 'expected_stop_amount', 'expected_target_amount',
        'pnl', 'entry_commission', 'exit_commission', 'funding_fee',
    )

    assert table.count('<th>') == len(expected_fields)
    assert f'colspan="{len(expected_fields)}"' in renderer
    assert 'trades.slice(-50)' in renderer
    for field in expected_fields:
        assert f't.{field}' in renderer


def test_funds_grid_has_independent_responsive_columns() -> None:
    _, _, css = _sources()

    assert '.form-grid {' in css
    assert 'grid-template-columns: repeat(4, minmax(0, 1fr));' in css
    assert '.funds-grid {' in css
    assert 'grid-template-columns: repeat(3, minmax(0, 1fr));' in css
    medium = css.split('@media (max-width: 800px)', 1)[1].split('@media (max-width: 520px)', 1)[0]
    small = css.split('@media (max-width: 520px)', 1)[1]
    assert '.funds-grid' in medium
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr));' in medium
    assert '.funds-grid' in small
    assert 'grid-template-columns: minmax(0, 1fr);' in small


def test_non_2xx_errors_use_api_detail_and_cache_key_is_updated() -> None:
    template, script, _ = _sources()

    assert script.count('if (!resp.ok)') >= 1
    assert 'formatApiError(data)' in script
    assert "if (!resp.ok)" in script
    assert "if (!created.success)" in script
    assert 'formatApiError(created)' in script
    assert '/static/js/backtest.js?v=signal-margin-1' in template


def test_equity_chart_uses_value_aware_tick_labels() -> None:
    _, script, _ = _sources()

    assert 'function formatEquityTick(value)' in script
    assert 'callback: formatEquityTick' in script
    assert "(v / 1000).toFixed(0) + 'k'" not in script
