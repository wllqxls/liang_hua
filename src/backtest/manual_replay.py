"""Deterministic server-side manual decision replay over closed local candles."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from src.backtest.engine import BacktestEngine
from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.signal_models import MarginMode, Signal, SignalMode


ReplayState = Literal['RUNNING', 'AWAITING_DECISION', 'FINISHED']
Decision = Literal['BUY', 'SELL', 'SKIP']
SIGNAL_TIMEFRAME_SECONDS = {'5m': 5 * 60, '15m': 15 * 60}
DISPLAY_REASONS = {
    'False break below the previous 20-candle low': '跌破前 20 根 K 线低点后重新收回，可能是假跌破',
    'False break above the previous 20-candle high': '突破前 20 根 K 线高点后重新跌回，可能是假突破',
    'RSI oversold with lower Bollinger Band reclaim': 'RSI 超卖后重新站上布林带下轨，出现反弹候选',
    'RSI overbought with upper Bollinger Band reclaim': 'RSI 超买后重新跌回布林带上轨下方，出现回落候选',
}


@dataclass(frozen=True, slots=True)
class ManualTrade:
    signal_time: pd.Timestamp
    side: Literal['BUY', 'SELL']
    fill_time: pd.Timestamp
    fill_price: float
    stop_price: float
    target_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: Literal['STOP', 'TARGET', 'FINALIZE']
    pnl: float
    equity: float


@dataclass(slots=True)
class ManualReplay:
    """A single replay that never exposes candles beyond its server cursor."""

    session_id: str
    symbol: str
    timeframe: str
    year: int
    mode: SignalMode
    snapshots: pd.Series
    chart_frames: dict[str, pd.DataFrame]
    cash: float
    opening_amount: float
    leverage: float
    taker_fee: float
    slippage_rate: float
    cursor: int = 0
    state: ReplayState = 'RUNNING'
    pending_signal: Signal | None = None
    decisions: list[dict[str, object]] = field(default_factory=list)
    trades: list[ManualTrade] = field(default_factory=list)
    equity_points: list[tuple[pd.Timestamp, float]] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        data_dir: Path,
        symbol: str,
        timeframe: str,
        year: int,
        mode: SignalMode,
        cash: float,
        opening_amount: float,
        leverage: float,
        taker_fee: float,
        slippage_rate: float,
    ) -> 'ManualReplay':
        if timeframe not in {'5m', '15m'}:
            raise ValueError('manual replay signal timeframe must be 5m or 15m')
        if opening_amount > cash:
            raise ValueError('opening amount must not exceed cash')
        engine = BacktestEngine(data_dir=data_dir)
        safe_symbol = symbol.replace('/', '_')
        paths = {
            timeframe: data_dir / f'{safe_symbol}_{timeframe}.csv',
            '1h': data_dir / f'{safe_symbol}_1h.csv',
            '4h': data_dir / f'{safe_symbol}_4h.csv',
        }
        if any(not path.exists() for path in paths.values()):
            raise FileNotFoundError('manual replay requires local entry, 1h, and 4h CSV data')
        snapshots = engine._load_signal_snapshots(  # noqa: SLF001 - controlled local adapter
            safe_symbol=safe_symbol,
            timeframe=timeframe,
            paths=paths,
        )
        start = pd.Timestamp(f'{year}-01-01', tz='UTC')
        end = pd.Timestamp(f'{year + 1}-01-01', tz='UTC')
        snapshots = snapshots.loc[(snapshots.index >= start) & (snapshots.index < end)]
        if snapshots.empty:
            raise ValueError('selected year has no replayable closed snapshots')
        chart_frames: dict[str, pd.DataFrame] = {}
        for chart_timeframe in ('5m', '15m', '1h'):
            path = data_dir / f'{safe_symbol}_{chart_timeframe}.csv'
            if not path.exists():
                raise FileNotFoundError('manual replay requires local chart CSV data')
            frame = engine.load_data(path).copy()
            frame.index = pd.to_datetime(frame.index, utc=True)
            chart_frames[chart_timeframe] = frame.loc[
                (frame.index >= start) & (frame.index < end)
            ]
        return cls(
            session_id=session_id,
            symbol=symbol,
            timeframe=timeframe,
            year=year,
            mode=mode,
            snapshots=snapshots,
            chart_frames=chart_frames,
            cash=float(cash),
            opening_amount=float(opening_amount),
            leverage=float(leverage),
            taker_fee=float(taker_fee),
            slippage_rate=float(slippage_rate),
            equity_points=[(snapshots.index[0], float(cash))],
        )

    def advance(self, *, max_bars: int = 40) -> None:
        """Move through closed bars until an eligible signal pauses the replay."""
        if self.state != 'RUNNING':
            return
        remaining = max(1, min(max_bars, 500))
        while remaining and self.cursor < len(self.snapshots):
            snapshot = self.snapshots.iloc[self.cursor]
            signal = dispatch_signal(snapshot, self.mode)
            if signal is not None:
                self.pending_signal = signal
                self.state = 'AWAITING_DECISION'
                return
            self.cursor += 1
            remaining -= 1
        if self.cursor >= len(self.snapshots) - 1:
            self.cursor = len(self.snapshots) - 1
            self.state = 'FINISHED'

    def decide(self, decision: Decision) -> None:
        """Record an immutable human decision and resolve accepted trades conservatively."""
        if self.state != 'AWAITING_DECISION' or self.pending_signal is None:
            raise ValueError('replay is not waiting for a decision')
        signal = self.pending_signal
        self.decisions.append({
            'timestamp': signal.signal_time.isoformat(),
            'time': _signal_candle_time(signal, self.timeframe),
            'suggested_side': signal.side,
            'decision': decision,
            'reason': _display_reason(signal.reason),
            'summary': _signal_summary(signal.side),
        })
        self.pending_signal = None
        if decision == 'SKIP':
            self.cursor += 1
            self.state = 'RUNNING' if self.cursor < len(self.snapshots) - 1 else 'FINISHED'
            return
        self._resolve_trade(signal, decision)
        self.state = 'RUNNING' if self.cursor < len(self.snapshots) - 1 else 'FINISHED'

    def visible_payload(self) -> dict[str, object]:
        """Expose only the completed replay prefix, never the unseen future suffix."""
        visible_end = min(self.cursor + 1, len(self.snapshots))
        start = max(0, visible_end - 500)
        visible = self.snapshots.iloc[start:visible_end]
        cursor_time = visible.index[-1]
        signal_payload = _signal_payload(self.pending_signal, self.timeframe) if self.pending_signal else None
        return {
            'session_id': self.session_id,
            'state': self.state,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'year': self.year,
            'candles': [_candle_payload(snapshot) for snapshot in visible],
            'charts': {
                timeframe: _chart_frame_payload(frame, cursor_time, timeframe)
                for timeframe, frame in self.chart_frames.items()
            },
            'signal': signal_payload,
            'signal_markers': [*self.decisions, *([signal_payload] if signal_payload else [])],
            'trades': [_trade_payload(trade) for trade in self.trades],
            'equity_curve': [
                {'timestamp': timestamp.isoformat(), 'equity': equity}
                for timestamp, equity in self.equity_points
            ],
            'cursor_time': cursor_time.isoformat(),
            'decisions': len(self.decisions),
        }

    def persist(self, root: Path) -> Path:
        """Persist only decisions and completed trades as a reproducible local artifact."""
        destination = root / f'{self.session_id}.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self.visible_payload()
        payload['trades'] = [asdict(trade) for trade in self.trades]
        destination.write_text(json.dumps(payload, default=str, ensure_ascii=False, indent=2), encoding='utf-8')
        return destination

    def _resolve_trade(self, signal: Signal, decision: Literal['BUY', 'SELL']) -> None:
        entry_index = self.cursor + 1
        if entry_index >= len(self.snapshots):
            self.cursor = len(self.snapshots) - 1
            return
        entry = self.snapshots.iloc[entry_index]
        fill_price = _adverse_fill(decision, entry.open, self.slippage_rate)
        distance_stop = signal.stop_distance
        distance_target = signal.target_distance
        direction = 1 if decision == 'BUY' else -1
        stop_price = fill_price - direction * distance_stop
        target_price = fill_price + direction * distance_target
        quantity = self.opening_amount * self.leverage / fill_price
        entry_fee = self.opening_amount * self.leverage * self.taker_fee
        self.cash -= entry_fee
        exit_index = entry_index
        exit_price = entry.close
        exit_reason: Literal['STOP', 'TARGET', 'FINALIZE'] = 'FINALIZE'
        for index in range(entry_index, len(self.snapshots)):
            candle = self.snapshots.iloc[index]
            if decision == 'BUY':
                if candle.low <= stop_price:
                    exit_price, exit_reason, exit_index = stop_price, 'STOP', index
                    break
                if candle.high >= target_price:
                    exit_price, exit_reason, exit_index = target_price, 'TARGET', index
                    break
            else:
                if candle.high >= stop_price:
                    exit_price, exit_reason, exit_index = stop_price, 'STOP', index
                    break
                if candle.low <= target_price:
                    exit_price, exit_reason, exit_index = target_price, 'TARGET', index
                    break
            exit_price, exit_index = candle.close, index
        exit_price = _adverse_fill('SELL' if decision == 'BUY' else 'BUY', exit_price, self.slippage_rate)
        gross = quantity * (exit_price - fill_price) * direction
        exit_fee = quantity * exit_price * self.taker_fee
        self.cash += gross - exit_fee
        exit_snapshot = self.snapshots.iloc[exit_index]
        trade = ManualTrade(
            signal_time=signal.signal_time,
            side=decision,
            fill_time=entry.opened_at,
            fill_price=fill_price,
            stop_price=stop_price,
            target_price=target_price,
            exit_time=exit_snapshot.closed_at,
            exit_price=exit_price,
            exit_reason=exit_reason,
            pnl=gross - entry_fee - exit_fee,
            equity=self.cash,
        )
        self.trades.append(trade)
        self.equity_points.append((trade.exit_time, self.cash))
        self.cursor = exit_index + 1


def _adverse_fill(side: Literal['BUY', 'SELL'], price: float, slippage: float) -> float:
    return price * (1 + slippage if side == 'BUY' else 1 - slippage)


def _candle_payload(snapshot: object) -> dict[str, object]:
    item = snapshot
    return {
        'time': int(item.opened_at.timestamp()),
        'open': item.open,
        'high': item.high,
        'low': item.low,
        'close': item.close,
    }


def _chart_frame_payload(frame: pd.DataFrame, cursor_time: pd.Timestamp, timeframe: str) -> list[dict[str, object]]:
    duration = {'5m': pd.Timedelta(minutes=5), '15m': pd.Timedelta(minutes=15), '1h': pd.Timedelta(hours=1)}[timeframe]
    visible = frame.loc[(frame.index + duration) <= cursor_time].tail(500)
    return [
        {
            'time': int(timestamp.timestamp()),
            'open': float(row['Open']),
            'high': float(row['High']),
            'low': float(row['Low']),
            'close': float(row['Close']),
        }
        for timestamp, row in visible.iterrows()
    ]


def _signal_payload(signal: Signal | None, timeframe: str) -> dict[str, object] | None:
    if signal is None:
        return None
    return {
        'time': _signal_candle_time(signal, timeframe),
        'side': signal.side,
        'reason': _display_reason(signal.reason),
        'score': signal.score,
        'summary': _signal_summary(signal.side),
        'stop_price': signal.estimated_stop_price,
        'target_price': signal.estimated_target_price,
    }


def _signal_summary(side: Literal['BUY', 'SELL']) -> str:
    return f'候选{"做多" if side == "BUY" else "做空"}'


def _signal_candle_time(signal: Signal, timeframe: str) -> int:
    return int(signal.signal_time.timestamp()) - SIGNAL_TIMEFRAME_SECONDS[timeframe]


def _display_reason(reason: str) -> str:
    return DISPLAY_REASONS.get(reason, reason)


def _trade_payload(trade: ManualTrade) -> dict[str, object]:
    return {
        'signal_time': trade.signal_time.isoformat(),
        'side': trade.side,
        'fill_time': trade.fill_time.isoformat(),
        'fill_price': trade.fill_price,
        'exit_time': trade.exit_time.isoformat(),
        'exit_price': trade.exit_price,
        'exit_reason': trade.exit_reason,
        'pnl': trade.pnl,
        'equity': trade.equity,
    }
