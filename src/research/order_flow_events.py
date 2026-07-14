"""Read-only research for order-flow impulse plus open-interest confirmation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src.research.event_factors import FIXED_ROUND_TRIP_COST, MINIMUM_BUCKET_SAMPLES


ENTRY_TIMEFRAME = pd.Timedelta(minutes=5)
FEATURE_WINDOW_BARS = 20
IMPULSE_BARS = 3
EVENT_COOLDOWN_BARS = 12
IMBALANCE_THRESHOLD = 0.30
VOLUME_RATIO_THRESHOLD = 1.50
PRICE_IMPULSE_THRESHOLD = 0.0015
OI_CHANGE_THRESHOLD = 0.002
PRIMARY_HORIZON = '15m'
HORIZONS = {
    '5m': 1,
    '15m': 3,
    '1h': 12,
}
REQUIRED_COLUMNS = {
    'close',
    'volume',
    'order_flow_imbalance',
    'sum_open_interest',
    'metrics_available',
}
SUMMARY_COLUMNS = (
    'horizon',
    'factor',
    'bucket',
    'samples',
    'average_gross_return',
    'average_net_return',
    'win_rate_pct',
    'profit_factor',
    'meets_minimum_sample',
)


@dataclass(frozen=True, slots=True)
class OrderFlowResearchSlice:
    """One symbol/year research result and the path of its derived events."""

    symbol: str
    year: int
    events: int
    eligible_rows: int
    excluded_metric_rows: int
    dataset_path: Path
    summary: pd.DataFrame


def load_order_flow_year(root: Path, *, symbol: str, year: int) -> pd.DataFrame:
    """Load one normalized annual package with timestamps in UTC."""
    path = (
        root
        / 'normalized'
        / 'order_flow_5m'
        / symbol
        / str(year)
        / f'{symbol}-order-flow-5m-{year}.csv'
    )
    frame = pd.read_csv(path)
    _validate_order_flow_frame(frame, name=str(path))
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True, format='mixed')
    return frame.set_index('timestamp').sort_index()


def load_funding_year(root: Path, *, symbol: str, year: int) -> pd.Series:
    """Return the latest already-settled funding rate at each source timestamp."""
    path = (
        root
        / 'normalized'
        / 'fundingRate'
        / symbol
        / str(year)
        / f'{symbol}-fundingRate-{year}.csv'
    )
    frame = pd.read_csv(path, usecols=['timestamp', 'last_funding_rate'])
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True, format='mixed')
    if frame['timestamp'].isna().any() or frame['timestamp'].duplicated().any():
        raise ValueError(f'{path} has invalid or duplicate funding timestamps')
    rate = pd.to_numeric(frame['last_funding_rate'], errors='coerce')
    if rate.isna().any() or not np.isfinite(rate).all():
        raise ValueError(f'{path} has invalid funding rates')
    return pd.Series(rate.to_numpy(dtype=float), index=frame['timestamp'], name='funding_rate').sort_index()


def build_order_flow_impulse_events(
    order_flow: pd.DataFrame,
    *,
    funding_rate: pd.Series | None = None,
) -> tuple[pd.DataFrame, int, int]:
    """Build frozen 5m impulse events using only information known at the close."""
    validated = _validated_order_flow(order_flow)
    features = _build_features(validated, funding_rate=funding_rate)
    metric_window_ok = features['metrics_available'].rolling(
        FEATURE_WINDOW_BARS + 1,
        min_periods=FEATURE_WINDOW_BARS + 1,
    ).sum().eq(FEATURE_WINDOW_BARS + 1)
    enough_history = features['volume_baseline'].notna() & features['oi_change_15m'].notna()
    directional_impulse = (
        features['price_change_15m'].abs().ge(PRICE_IMPULSE_THRESHOLD)
        & np.sign(features['price_change_15m']).eq(np.sign(features['order_flow_imbalance']))
    )
    qualified = (
        metric_window_ok
        & enough_history
        & features['order_flow_imbalance'].abs().ge(IMBALANCE_THRESHOLD)
        & features['volume_ratio'].ge(VOLUME_RATIO_THRESHOLD)
        & directional_impulse
        & features['oi_change_15m'].ge(OI_CHANGE_THRESHOLD)
    )
    events = _apply_cooldown(features.loc[qualified].copy())
    events['side'] = np.where(events['order_flow_imbalance'].gt(0), 'BUY', 'SELL')
    direction = np.where(events['side'].eq('BUY'), 1.0, -1.0)
    for horizon, bars in HORIZONS.items():
        future_close = features['close'].shift(-bars).reindex(events.index)
        gross_return = direction * (future_close / events['close'] - 1.0)
        events[f'forward_return_{horizon}'] = gross_return
        events[f'forward_return_{horizon}_net'] = gross_return - FIXED_ROUND_TRIP_COST
    events.index.name = 'timestamp'
    eligible_rows = int(qualified.sum())
    excluded_metric_rows = int((enough_history & ~metric_window_ok).sum())
    return events, eligible_rows, excluded_metric_rows


def summarize_order_flow_events(events: pd.DataFrame) -> pd.DataFrame:
    """Summarize all frozen factor buckets at every fixed label horizon."""
    required = {'side', 'order_flow_imbalance', 'oi_change_15m', 'atr_pct'}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f'events is missing required columns: {", ".join(missing)}')
    summaries: list[pd.DataFrame] = []
    working = events.copy()
    working['overall'] = 'ALL'
    working['imbalance_tertile'] = _tertiles(working['order_flow_imbalance'].abs())
    working['oi_change_tertile'] = _tertiles(working['oi_change_15m'])
    working['volatility_tertile'] = _tertiles(working['atr_pct'])
    working['funding_tertile'] = _tertiles(working['funding_rate'])
    factors = (
        ('overall', 'overall'),
        ('direction', 'side'),
        ('imbalance_tertile', 'imbalance_tertile'),
        ('oi_change_tertile', 'oi_change_tertile'),
        ('volatility_tertile', 'volatility_tertile'),
        ('funding_tertile', 'funding_tertile'),
    )
    for horizon in HORIZONS:
        gross_column = f'forward_return_{horizon}'
        net_column = f'forward_return_{horizon}_net'
        if gross_column not in working or net_column not in working:
            raise ValueError(f'events is missing horizon labels for {horizon}')
        usable = working.dropna(subset=[gross_column, net_column])
        for factor, column in factors:
            summaries.append(
                _summarize_factor(
                    usable,
                    horizon=horizon,
                    factor=factor,
                    bucket_column=column,
                    gross_column=gross_column,
                    net_column=net_column,
                )
            )
    if not summaries:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    return pd.concat(summaries, ignore_index=True)


def run_order_flow_impulse_research(
    *,
    data_root: Path,
    output_root: Path,
    years: Iterable[int] = (2024, 2025),
    symbols: Iterable[str] = ('BTCUSDT', 'ETHUSDT'),
) -> list[OrderFlowResearchSlice]:
    """Materialize reproducible event CSVs and summaries for the frozen study."""
    output_root.mkdir(parents=True, exist_ok=True)
    slices: list[OrderFlowResearchSlice] = []
    for year in years:
        for symbol in symbols:
            order_flow = load_order_flow_year(data_root, symbol=symbol, year=year)
            funding = load_funding_year(data_root, symbol=symbol, year=year)
            events, eligible_rows, excluded_metric_rows = build_order_flow_impulse_events(
                order_flow,
                funding_rate=funding,
            )
            dataset_path = output_root / f'{symbol}_5m_{year}_impulse_oi_events.csv'
            events.to_csv(dataset_path)
            slices.append(
                OrderFlowResearchSlice(
                    symbol=symbol,
                    year=year,
                    events=len(events),
                    eligible_rows=eligible_rows,
                    excluded_metric_rows=excluded_metric_rows,
                    dataset_path=dataset_path,
                    summary=summarize_order_flow_events(events),
                )
            )
    return slices


def primary_validation_passed(slices: Iterable[OrderFlowResearchSlice]) -> bool:
    """Require both 2025 symbols to clear the predeclared 15m aggregate gate."""
    target = [item for item in slices if item.year == 2025]
    if {item.symbol for item in target} != {'BTCUSDT', 'ETHUSDT'}:
        return False
    for item in target:
        primary = item.summary.loc[
            (item.summary['horizon'] == PRIMARY_HORIZON)
            & (item.summary['factor'] == 'overall')
            & (item.summary['bucket'] == 'ALL')
        ]
        if len(primary) != 1:
            return False
        row = primary.iloc[0]
        if not (
            int(row['samples']) >= MINIMUM_BUCKET_SAMPLES
            and float(row['average_net_return']) > 0
            and float(row['profit_factor']) >= 1.15
        ):
            return False
    return True


def _validated_order_flow(frame: pd.DataFrame) -> pd.DataFrame:
    _validate_order_flow_frame(frame, name='order_flow')
    result = frame.copy()
    if not isinstance(result.index, pd.DatetimeIndex):
        raise ValueError('order_flow index must be a DatetimeIndex')
    if result.index.tz is None:
        result.index = result.index.tz_localize('UTC')
    else:
        result.index = result.index.tz_convert('UTC')
    if result.index.has_duplicates or not result.index.is_monotonic_increasing:
        raise ValueError('order_flow timestamps must be unique and sorted')
    numeric_columns = REQUIRED_COLUMNS - {'metrics_available', 'sum_open_interest'}
    for column in numeric_columns | {'sum_open_interest'}:
        result[column] = pd.to_numeric(result[column], errors='coerce')
    if result[list(numeric_columns)].isna().any().any():
        raise ValueError('order_flow has invalid numeric values')
    result['metrics_available'] = _as_boolean(result['metrics_available'])
    if result['metrics_available'].isna().any():
        raise ValueError('metrics_available has invalid values')
    if result.loc[result['metrics_available'], 'sum_open_interest'].isna().any():
        raise ValueError('available metrics rows must have open interest')
    return result


def _validate_order_flow_frame(frame: pd.DataFrame, *, name: str) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f'{name} is missing required columns: {", ".join(missing)}')


def _build_features(
    frame: pd.DataFrame,
    *,
    funding_rate: pd.Series | None,
) -> pd.DataFrame:
    features = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    features['volume_baseline'] = features['volume'].rolling(
        FEATURE_WINDOW_BARS,
        min_periods=FEATURE_WINDOW_BARS,
    ).mean().shift(1)
    features['volume_ratio'] = features['volume'] / features['volume_baseline']
    features['price_change_15m'] = features['close'] / features['close'].shift(IMPULSE_BARS) - 1.0
    features['oi_change_15m'] = (
        features['sum_open_interest'] / features['sum_open_interest'].shift(IMPULSE_BARS) - 1.0
    )
    true_range = pd.concat(
        (
            features['close'].diff().abs(),
            pd.Series(0.0, index=features.index),
        ),
        axis=1,
    ).max(axis=1)
    features['atr_pct'] = true_range.rolling(14, min_periods=14).mean() / features['close']
    if funding_rate is None:
        features['funding_rate'] = math.nan
    else:
        funding = funding_rate.copy()
        if not isinstance(funding.index, pd.DatetimeIndex):
            raise ValueError('funding_rate index must be a DatetimeIndex')
        if funding.index.tz is None:
            funding.index = funding.index.tz_localize('UTC')
        else:
            funding.index = funding.index.tz_convert('UTC')
        if funding.index.has_duplicates or not funding.index.is_monotonic_increasing:
            raise ValueError('funding_rate timestamps must be unique and sorted')
        features['funding_rate'] = funding.reindex(features.index, method='ffill')
    return features


def _apply_cooldown(candidates: pd.DataFrame) -> pd.DataFrame:
    selected: list[pd.Timestamp] = []
    last_position: int | None = None
    for timestamp, row in candidates.iterrows():
        position = int(row.name.value // ENTRY_TIMEFRAME.value)
        if last_position is None or position - last_position >= EVENT_COOLDOWN_BARS:
            selected.append(timestamp)
            last_position = position
    return candidates.loc[selected].copy()


def _tertiles(values: pd.Series) -> pd.Series:
    result = pd.Series('UNAVAILABLE', index=values.index, dtype='object')
    valid = pd.to_numeric(values, errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
    if valid.empty:
        return result
    ranks = valid.rank(method='first')
    result.loc[valid.index] = pd.qcut(ranks, q=min(3, len(valid)), labels=False).astype(str)
    return result.replace({'0': 'LOW', '1': 'MID', '2': 'HIGH'})


def _summarize_factor(
    events: pd.DataFrame,
    *,
    horizon: str,
    factor: str,
    bucket_column: str,
    gross_column: str,
    net_column: str,
) -> pd.DataFrame:
    rows: list[dict[str, float | int | str | bool]] = []
    for bucket, group in events.groupby(bucket_column, dropna=False, sort=True):
        net = group[net_column].astype(float)
        gross = group[gross_column].astype(float)
        gains = float(net.loc[net > 0].sum())
        losses = float(-net.loc[net < 0].sum())
        profit_factor = math.inf if gains > 0 and losses == 0 else (gains / losses if losses else math.nan)
        rows.append(
            {
                'horizon': horizon,
                'factor': factor,
                'bucket': str(bucket),
                'samples': len(group),
                'average_gross_return': float(gross.mean()),
                'average_net_return': float(net.mean()),
                'win_rate_pct': float((net > 0).mean() * 100),
                'profit_factor': profit_factor,
                'meets_minimum_sample': len(group) >= MINIMUM_BUCKET_SAMPLES,
            }
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _as_boolean(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values
    return values.astype(str).str.lower().map({'true': True, 'false': False})
