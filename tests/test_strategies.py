from __future__ import annotations

from src.backtest.optimizer import build_stage_one_candidates
from src.strategies.risk import (
    build_long_risk_prices,
    build_risk_prices,
    calculate_fractional_order_size,
    estimate_liquidation_price,
    strong_context_trend_allows_side,
)
from src.strategies.signal_models import (
    DEFAULT_SIGNAL_PARAMETERS,
    MarginMode,
    SignalMode,
)
from src.web.routes import MODE_OPTIONS
from src.web.schemas import BacktestRequest


class FakeSeries:
    def __init__(self, value: float) -> None:
        self._value = value

    def __getitem__(self, index: int) -> float:
        return self._value


class FakeContextData:
    def __init__(
        self,
        trend: float | None,
        strength: float | None,
        momentum: float | None = None,
        close: float | None = None,
        fast_ma: float | None = None,
    ) -> None:
        if trend is not None:
            self.ContextTrend = FakeSeries(trend)
        if strength is not None:
            self.ContextTrendStrength = FakeSeries(strength)
        if momentum is not None:
            self.ContextTrendMomentum = FakeSeries(momentum)
        if close is not None:
            self.ContextClose = FakeSeries(close)
        if fast_ma is not None:
            self.ContextFastMA = FakeSeries(fast_ma)


def test_index_exposes_only_stable_signal_modes() -> None:
    assert [item['value'] for item in MODE_OPTIONS] == [
        'KEY_LEVEL',
        'RSI_REVERSAL',
        'KEY_LEVEL_RSI',
    ]


def test_api_schema_exposes_only_stable_signal_modes() -> None:
    schema = BacktestRequest.model_json_schema()
    mode_ref = schema['properties']['mode']['$ref'].split('/')[-1]

    assert schema['$defs'][mode_ref]['enum'] == [
        'KEY_LEVEL',
        'RSI_REVERSAL',
        'KEY_LEVEL_RSI',
    ]


def test_optimizer_candidates_cover_only_stable_signal_modes() -> None:
    candidates = build_stage_one_candidates(
        entry_timeframes=['5m'],
        modes=list(SignalMode),
        margin_mode=MarginMode.ISOLATED,
        current_leverage=5,
        seed_key='stable-modes',
    )

    assert {candidate.mode.value for candidate in candidates} == {
        'KEY_LEVEL',
        'RSI_REVERSAL',
        'KEY_LEVEL_RSI',
    }


def test_optimizer_candidates_include_non_default_signal_parameters() -> None:
    candidates = build_stage_one_candidates(
        entry_timeframes=['5m'],
        modes=list(SignalMode),
        margin_mode=MarginMode.ISOLATED,
        current_leverage=5,
        seed_key='signal-parameters',
    )

    assert any(
        candidate.signal_parameters != DEFAULT_SIGNAL_PARAMETERS
        for candidate in candidates
    )


def test_fractional_order_size_uses_margin_and_leverage() -> None:
    size = calculate_fractional_order_size(
        price=0.0006,
        equity=10,
        position_amount=3.3,
        leverage=5,
    )

    assert size == 27_500


def test_long_risk_prices_use_usdt_amounts() -> None:
    take_profit, stop_loss = build_long_risk_prices(
        price=100.0,
        position_amount=3.3,
        leverage=20,
        take_profit_amount=6.0,
        stop_loss_amount=2.0,
    )

    assert round(take_profit, 4) == 109.0909
    assert round(stop_loss, 4) == 96.9697


def test_short_risk_prices_use_usdt_amounts_and_liquidation_cap() -> None:
    take_profit, stop_loss = build_risk_prices(
        side="short",
        price=100.0,
        position_amount=3.3,
        leverage=20,
        take_profit_amount=6.0,
        stop_loss_amount=10.0,
    )

    assert round(take_profit, 4) == 90.9091
    assert round(stop_loss, 4) == 104.5


def test_liquidation_price_is_side_aware() -> None:
    assert estimate_liquidation_price("long", 100.0, 20, 0.005) == 95.5
    assert round(estimate_liquidation_price("short", 100.0, 20, 0.005), 4) == 104.5


def test_strong_context_trend_requires_alignment() -> None:
    data = FakeContextData(trend=1, strength=1.2, momentum=0.2, close=110, fast_ma=100)

    assert strong_context_trend_allows_side(data, 'long') is True
    assert strong_context_trend_allows_side(data, 'short') is False


def test_strong_context_trend_allows_strong_downtrend_short() -> None:
    data = FakeContextData(trend=-1, strength=1.2, momentum=-0.2, close=90, fast_ma=100)

    assert strong_context_trend_allows_side(data, 'short') is True
    assert strong_context_trend_allows_side(data, 'long') is False


def test_strong_context_trend_rejects_weak_or_missing_context() -> None:
    assert strong_context_trend_allows_side(
        FakeContextData(1, 0.99, 0.2, 110, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(1, None, 0.2, 110, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(None, 1.2, 0.2, 110, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(1, 1.2, None, 110, 100), 'long'
    ) is False


def test_strong_context_trend_rejects_reversing_momentum() -> None:
    assert strong_context_trend_allows_side(
        FakeContextData(1, 1.2, -0.1, 110, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(-1, 1.2, 0.1, 90, 100), 'short'
    ) is False


def test_strong_context_trend_rejects_wrong_price_position() -> None:
    assert strong_context_trend_allows_side(
        FakeContextData(1, 1.2, 0.2, 90, 100), 'long'
    ) is False
    assert strong_context_trend_allows_side(
        FakeContextData(-1, 1.2, -0.2, 110, 100), 'short'
    ) is False
