"""Rank visual, statistically positive signal profiles for human replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pandas as pd

from src.backtest.engine import BacktestEngine
from src.backtest.optimizer import SIGNAL_PARAMETER_OPTIONS
from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.signal_models import ACTIVE_SIGNAL_MODES, SignalMode, SignalParameters


HOLD_BARS = {'5m': 48, '15m': 16}


@dataclass(frozen=True, slots=True)
class WhiteListItem:
    rank: int
    symbol: str
    mode: str
    timeframe: str
    parameters: SignalParameters
    events_2024: int
    events_2025: int
    gross_return_2024: float
    gross_return_2025: float
    visual_score: float
    sample_score: float
    trigger_logic: str


def build_semi_auto_whitelist(data_root: Path, *, symbol: str) -> list[WhiteListItem]:
    """Use 2024 ranking and 2025 confirmation without any net-profit objective."""
    rows: list[WhiteListItem] = []
    snapshot_cache = {
        (year, timeframe): _load_snapshots(data_root, symbol, year, timeframe)
        for year in (2024, 2025)
        for timeframe in ('5m', '15m')
    }
    for mode in ACTIVE_SIGNAL_MODES:
        for timeframe in ('5m', '15m'):
            for parameters in SIGNAL_PARAMETER_OPTIONS:
                metrics = {
                    year: _candidate_metrics(
                        snapshot_cache[(year, timeframe)], timeframe, mode, parameters
                    )
                    for year in (2024, 2025)
                }
                first, second = metrics[2024], metrics[2025]
                if not (30 <= first['events'] <= 100 and 30 <= second['events'] <= 100):
                    continue
                if first['gross_return'] <= 0 or second['gross_return'] <= 0:
                    continue
                rows.append(WhiteListItem(
                    rank=0, symbol=symbol, mode=mode.value, timeframe=timeframe,
                    parameters=parameters, events_2024=first['events'], events_2025=second['events'],
                    gross_return_2024=first['gross_return'], gross_return_2025=second['gross_return'],
                    visual_score=(first['visual_score'] + second['visual_score']) / 2,
                    sample_score=(first['sample_score'] + second['sample_score']) / 2,
                    trigger_logic=_trigger_logic(mode),
                ))
    rows.sort(key=lambda item: (item.visual_score, item.sample_score, item.gross_return_2024), reverse=True)
    return [replace(item, rank=index) for index, item in enumerate(rows[:5], start=1)]


def write_semi_auto_whitelist(items: list[WhiteListItem], destination: Path) -> None:
    """Write the only optimizer deliverable: a compact human-signal whitelist CSV."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in items:
        row = asdict(item)
        row['parameters'] = str(asdict(item.parameters))
        rows.append(row)
    columns = [
        'rank', 'symbol', 'mode', 'timeframe', 'parameters', 'events_2024',
        'events_2025', 'gross_return_2024', 'gross_return_2025',
        'visual_score', 'sample_score', 'trigger_logic',
    ]
    pd.DataFrame(rows, columns=columns).to_csv(destination, index=False, encoding='utf-8-sig')


def _load_snapshots(data_root: Path, symbol: str, year: int, timeframe: str) -> pd.Series:
    engine = BacktestEngine(data_dir=data_root / str(year))
    safe = symbol.replace('/', '_')
    paths = {timeframe: data_root / str(year) / f'{safe}_{timeframe}.csv', '1h': data_root / str(year) / f'{safe}_1h.csv', '4h': data_root / str(year) / f'{safe}_4h.csv'}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f'semi-auto whitelist requires local CSV data: {missing}')
    return engine._load_signal_snapshots(  # noqa: SLF001 - controlled local adapter
        safe_symbol=safe,
        timeframe=timeframe,
        paths=paths,
    )


def _candidate_metrics(snapshots: pd.Series, timeframe: str, mode: SignalMode, parameters: SignalParameters) -> dict[str, float | int]:
    events: list[tuple[float, float]] = []
    horizon = HOLD_BARS[timeframe]
    for index in range(0, len(snapshots) - horizon):
        snapshot = snapshots.iloc[index]
        signal = dispatch_signal(snapshot, mode, parameters=parameters)
        if signal is None:
            continue
        future_close = snapshots.iloc[index + horizon].close
        direction = 1 if signal.side == 'BUY' else -1
        gross = direction * (future_close / signal.signal_close - 1)
        body = abs(snapshot.close - snapshot.open) / snapshot.atr
        upper = (snapshot.high - max(snapshot.open, snapshot.close)) / snapshot.atr
        lower = (min(snapshot.open, snapshot.close) - snapshot.low) / snapshot.atr
        events.append((gross, max(body, upper, lower)))
    count = len(events)
    return {
        'events': count,
        'gross_return': sum(item[0] for item in events) / count if count else 0.0,
        'visual_score': sum(item[1] for item in events) / count if count else 0.0,
        'sample_score': max(0.0, 1 - abs(count - 65) / 35),
    }


def _trigger_logic(mode: SignalMode) -> str:
    return {
        SignalMode.KEY_LEVEL: '关键位假突破/假跌破后收回',
        SignalMode.RSI_REVERSAL: 'RSI 极值与布林带收回',
        SignalMode.KEY_LEVEL_RSI: '关键位优先，RSI 作为补充',
    }[mode]
