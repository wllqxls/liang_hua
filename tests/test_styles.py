from pathlib import Path


STYLE_PATH = Path(__file__).parents[1] / 'static' / 'css' / 'style.css'
SCRIPT_PATH = Path(__file__).parents[1] / 'static' / 'js' / 'backtest.js'
TEMPLATE_PATH = Path(__file__).parents[1] / 'templates' / 'backtest.html'


def test_form_grid_has_explicit_responsive_columns() -> None:
    css = STYLE_PATH.read_text(encoding='utf-8')

    assert 'grid-template-columns: repeat(4, minmax(0, 1fr));' in css
    assert '@media (max-width: 800px)' in css
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr));' in css
    assert '@media (max-width: 520px)' in css
    assert 'grid-template-columns: minmax(0, 1fr);' in css


def test_optimizer_frontend_uses_jobs_and_applies_timeframes() -> None:
    script = SCRIPT_PATH.read_text(encoding='utf-8')
    template = TEMPLATE_PATH.read_text(encoding='utf-8')

    assert "fetch('/api/optimize/jobs'" in script
    assert "fetch('/api/optimize/jobs/' + jobId)" in script
    assert 'await delay(1000)' in script
    assert 'const validationError = validateOptimizationPayload(payload);' in script
    assert "document.getElementById('context-timeframe').value = item.context_timeframe" in script
    assert "document.getElementById('timeframe').value = item.timeframe" in script
    assert '<th>环境周期</th>' in template
    assert '<th>入场周期</th>' in template
    assert '<th>长窗口%</th>' in template


def test_equity_chart_uses_value_aware_tick_labels() -> None:
    script = SCRIPT_PATH.read_text(encoding='utf-8')

    assert 'function formatEquityTick(value)' in script
    assert 'callback: formatEquityTick' in script
    assert "(v / 1000).toFixed(0) + 'k'" not in script
