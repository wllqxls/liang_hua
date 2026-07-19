"""Adaptive 15m buy-pressure absorption candidates without future labels."""

from __future__ import annotations

import pandas as pd

from src.research.order_flow_fading_push import (
    EVENT_COOLDOWN_BARS,
    OI_LOOKBACK_BARS,
    _apply_cooldown,
    _build_features,
    _validated_frame,
)


ROLLING_WINDOW_BARS = 30 * 24 * 4
RELATIVE_QUANTILE = 0.80
FACTOR_ID = 'RELATIVE_ABSORPTION_V1'


def build_relative_absorption_candidates(
    fifteen_minute: pd.DataFrame,
    *,
    funding_rate: pd.Series | None = None,
    rolling_window_bars: int = ROLLING_WINDOW_BARS,
    relative_quantile: float = RELATIVE_QUANTILE,
    event_cooldown_bars: int = EVENT_COOLDOWN_BARS,
) -> tuple[pd.DataFrame, int, int]:
    """Return SELL candidates using only thresholds known before each event bar."""
    if rolling_window_bars < 20:
        raise ValueError('rolling_window_bars must be at least 20')
    if not 0 < relative_quantile < 1:
        raise ValueError('relative_quantile must be between 0 and 1')
    frame = _validated_frame(fifteen_minute)
    features = _build_features(frame, funding_rate=funding_rate)
    features['taker_ratio_threshold'] = (
        features['taker_buy_ratio'].shift(1).rolling(
            rolling_window_bars,
            min_periods=rolling_window_bars,
        ).quantile(relative_quantile)
    )
    features['oi_change_threshold'] = (
        features['oi_change_45m'].shift(1).rolling(
            rolling_window_bars,
            min_periods=rolling_window_bars,
        ).quantile(relative_quantile)
    )
    metric_window_ok = features['metrics_available'].rolling(
        OI_LOOKBACK_BARS + 1,
        min_periods=OI_LOOKBACK_BARS + 1,
    ).sum().eq(OI_LOOKBACK_BARS + 1)
    enough_history = features[
        ['previous_close', 'taker_ratio_threshold', 'oi_change_threshold']
    ].notna().all(axis=1)
    qualified = (
        metric_window_ok
        & enough_history
        & features['taker_buy_ratio'].gt(0.5)
        & features['oi_change_45m'].gt(0)
        & features['taker_buy_ratio'].ge(features['taker_ratio_threshold'])
        & features['oi_change_45m'].ge(features['oi_change_threshold'])
        & features['close'].lt(features['previous_close'])
    )
    events = _apply_cooldown(
        features.loc[qualified].copy(),
        cooldown_bars=event_cooldown_bars,
    )
    events['side'] = 'SELL'
    events['factor_id'] = FACTOR_ID
    events.index.name = 'timestamp'
    return events, int(qualified.sum()), int((enough_history & ~metric_window_ok).sum())
