"""Deterministic server-side manual decision replay over closed local candles."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Literal

import pandas as pd

from src.backtest.engine import BacktestEngine
from src.backtest.signal_simulator import funding_cash_flow
from src.data.yearly import MARKET_SOURCE, yearly_data_source
from src.research.order_flow_events import load_funding_year, load_order_flow_year
from src.research.order_flow_failed_push import aggregate_order_flow_to_15m
from src.research.order_flow_fading_push import build_fading_push_candidates
from src.research.order_flow_relative_absorption import build_relative_absorption_candidates
from src.strategies.key_level_v2 import (
    MIN_REWARD_RISK,
    build_key_level_candidates,
    structural_reward_risk,
)
from src.strategies.manual_candidates import (
    evaluate_manual_candidate,
    validate_manual_candidate_scope,
)
from src.strategies.signal_dispatcher import dispatch_signal
from src.strategies.risk import estimate_position_liquidation_price
from src.strategies.signal_models import (
    ManualSignalMode,
    MarginMode,
    MarketSnapshot,
    Signal,
    SignalMode,
)


ReplayState = Literal[
    'RUNNING',
    'AWAITING_DECISION',
    'POSITION_OPEN',
    'AWAITING_CONTINUE',
    'FINISHED',
]
Decision = Literal['BUY', 'SELL', 'SKIP']
ExitReason = Literal['STOP', 'TARGET', 'LIQUIDATION', 'TIME', 'FINALIZE']
SIGNAL_TIMEFRAME_SECONDS = {'5m': 5 * 60, '15m': 15 * 60}
EXIT_REASON_LABELS = {
    'STOP': '止损',
    'TARGET': '止盈',
    'LIQUIDATION': '强平',
    'TIME': '时间退出',
    'FINALIZE': '期末平仓',
}
MARGIN_MODE_LABELS = {
    MarginMode.ISOLATED: '逐仓',
    MarginMode.CROSS: '全仓',
}
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
    liquidation_price: float
    margin_mode: MarginMode
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: ExitReason
    liquidation_fee: float
    funding: float
    pnl: float
    equity: float


@dataclass(frozen=True, slots=True)
class ActivePosition:
    signal_time: pd.Timestamp
    side: Literal['BUY', 'SELL']
    entry_index: int
    fill_time: pd.Timestamp
    fill_price: float
    stop_price: float
    target_price: float
    liquidation_price: float
    margin_mode: MarginMode
    risk_warning: str | None
    quantity: float
    entry_fee: float
    funding: float
    funding_cursor: pd.Timestamp


@dataclass(slots=True)
class ManualReplay:
    """A single replay that never exposes candles beyond its server cursor."""

    session_id: str
    symbol: str
    timeframe: str
    year: int
    mode: ManualSignalMode | SignalMode
    snapshots: pd.Series
    chart_frames: dict[str, pd.DataFrame]
    cash: float
    opening_amount: float
    leverage: float
    taker_fee: float
    slippage_rate: float
    maximum_holding_bars: int | None = None
    whitelist_profile: dict[str, object] | None = None
    margin_mode: MarginMode = MarginMode.ISOLATED
    maintenance_margin_rate: float = 0.005
    liquidation_fee_rate: float = 0.005
    cursor: int = 0
    state: ReplayState = 'RUNNING'
    pending_signal: Signal | None = None
    active_position: ActivePosition | None = None
    decisions: list[dict[str, object]] = field(default_factory=list)
    trades: list[ManualTrade] = field(default_factory=list)
    equity_points: list[tuple[pd.Timestamp, float]] = field(default_factory=list)
    candidate_features: pd.DataFrame | None = None
    funding_rates: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        data_dir: Path,
        symbol: str,
        timeframe: str,
        year: int,
        mode: ManualSignalMode,
        cash: float,
        opening_amount: float,
        leverage: float,
        taker_fee: float,
        slippage_rate: float,
        margin_mode: MarginMode,
        maintenance_margin_rate: float,
        liquidation_fee_rate: float,
        order_flow_taker_threshold: float = 0.55,
        order_flow_oi_threshold: float = 0.002,
        maximum_holding_bars: int | None = None,
        whitelist_profile: dict[str, object] | None = None,
    ) -> 'ManualReplay':
        if timeframe not in {'5m', '15m'}:
            raise ValueError('manual replay signal timeframe must be 5m or 15m')
        if opening_amount > cash:
            raise ValueError('opening amount must not exceed cash')
        if opening_amount * leverage * taker_fee >= cash:
            raise ValueError('账户资金不足以支付开仓手续费')
        if maximum_holding_bars is not None and maximum_holding_bars < 1:
            raise ValueError('maximum holding bars must be positive')
        validate_manual_candidate_scope(
            mode=mode,
            symbol=symbol,
            timeframe=timeframe,
            year=year,
        )
        engine = BacktestEngine(data_dir=data_dir)
        safe_symbol = symbol.replace('/', '_')
        if yearly_data_source(data_dir.parent, symbol, year) != MARKET_SOURCE:
            raise ValueError('基础 K 线是旧现货或未知来源，请先在“本地数据”重新拉取该年度 USD-M 永续行情')
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
        order_flow_root = data_dir.parent / 'order_flow' / 'binance_um'
        order_flow_symbol = symbol.replace('/', '')
        try:
            funding_rates = _normalize_funding_rates(load_funding_year(
                order_flow_root,
                symbol=order_flow_symbol,
                year=year,
            ))
        except FileNotFoundError:
            funding_rates = pd.Series(dtype=float, name='funding_rate')
        candidate_features = None
        if mode is ManualSignalMode.KEY_LEVEL_V2:
            candidate_features = build_key_level_candidates(
                chart_frames[timeframe],
                taker_fee=taker_fee,
                slippage_rate=slippage_rate,
            )
        if mode in {
            ManualSignalMode.ORDER_FLOW_FADING_15M,
            ManualSignalMode.ORDER_FLOW_ABSORPTION_15M,
        }:
            if funding_rates.empty:
                raise FileNotFoundError('manual replay requires local historical funding rates')
            five_minute = load_order_flow_year(
                order_flow_root,
                symbol=order_flow_symbol,
                year=year,
            )
            fifteen_minute = aggregate_order_flow_to_15m(five_minute)
            if mode is ManualSignalMode.ORDER_FLOW_ABSORPTION_15M:
                candidate_features, _, _ = build_relative_absorption_candidates(
                    fifteen_minute,
                    funding_rate=funding_rates,
                )
            else:
                candidate_features, _, _ = build_fading_push_candidates(
                    fifteen_minute,
                    funding_rate=funding_rates,
                    taker_buy_ratio_threshold=order_flow_taker_threshold,
                    oi_change_threshold=order_flow_oi_threshold,
                )
                candidate_features['taker_buy_ratio_threshold'] = order_flow_taker_threshold
                candidate_features['oi_change_threshold'] = order_flow_oi_threshold
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
            maximum_holding_bars=maximum_holding_bars,
            whitelist_profile=whitelist_profile,
            margin_mode=margin_mode,
            maintenance_margin_rate=float(maintenance_margin_rate),
            liquidation_fee_rate=float(liquidation_fee_rate),
            equity_points=[(snapshots.index[0], float(cash))],
            candidate_features=candidate_features,
            funding_rates=funding_rates,
        )

    def advance(self, *, max_bars: int = 40) -> None:
        """Move through closed bars until an eligible signal pauses the replay."""
        if self.state != 'RUNNING':
            return
        remaining = max(1, min(max_bars, 500))
        while remaining and self.cursor < len(self.snapshots):
            snapshot = self.snapshots.iloc[self.cursor]
            signal = self._evaluate_snapshot(snapshot)
            if signal is not None:
                self.pending_signal = signal
                self.state = 'AWAITING_DECISION'
                return
            self.cursor += 1
            remaining -= 1
        if self.cursor >= len(self.snapshots) - 1:
            self.cursor = len(self.snapshots) - 1
            self.state = 'FINISHED'

    def _evaluate_snapshot(self, snapshot: MarketSnapshot) -> Signal | None:
        if isinstance(self.mode, SignalMode):
            return dispatch_signal(snapshot, self.mode)
        features = None
        if self.candidate_features is not None and snapshot.opened_at in self.candidate_features.index:
            features = self.candidate_features.loc[snapshot.opened_at]
        return evaluate_manual_candidate(
            snapshot,
            self.mode,
            order_flow_features=features,
        )

    def decide(self, decision: Decision) -> None:
        """Record an immutable human decision and open accepted positions."""
        if self.state != 'AWAITING_DECISION' or self.pending_signal is None:
            raise ValueError('replay is not waiting for a decision')
        signal = self.pending_signal
        if (
            signal.structural_risk is not None
            and decision not in {signal.side, 'SKIP'}
        ):
            raise ValueError('关键区域候选只能接受建议方向或放弃')
        signal_payload = _signal_payload(signal, self.timeframe)
        if signal_payload is None:
            raise ValueError('replay lost its pending signal')
        decision_record: dict[str, object] = {
            **signal_payload,
            'timestamp': signal.signal_time.isoformat(),
            'suggested_side': signal.side,
            'decision': decision,
        }
        if decision == 'SKIP':
            decision_record['entry_status'] = 'SKIPPED'
            self.decisions.append(decision_record)
            self.pending_signal = None
            self.cursor += 1
            self.state = 'RUNNING' if self.cursor < len(self.snapshots) - 1 else 'FINISHED'
            return
        entry_index = self.cursor + 1
        if entry_index >= len(self.snapshots):
            if signal.structural_risk is not None:
                decision_record['actual_reward_risk'] = None
            self._record_open_invalidation(
                decision_record,
                entry_index=entry_index,
                reason='候选后没有下一根已收盘 K 线，无法按下一根开盘成交',
            )
            return
        entry = self.snapshots.iloc[entry_index]
        decision_record['entry_open_price'] = entry.open
        try:
            prepared_position = self._prepare_position(signal, decision, entry_index)
        except ValueError as exc:
            if signal.structural_risk is not None:
                decision_record['actual_reward_risk'] = None
            self._record_open_invalidation(
                decision_record,
                entry_index=entry_index,
                reason=str(exc),
            )
            return
        decision_record['entry_fill_price'] = prepared_position.fill_price
        decision_record['resolved_stop_price'] = prepared_position.stop_price
        decision_record['resolved_target_price'] = prepared_position.target_price
        if signal.structural_risk is not None:
            actual_reward_risk = structural_reward_risk(
                side=signal.side,
                reference_price=entry.open,
                stop_price=signal.structural_risk.stop_price,
                target_price=signal.structural_risk.target_price,
                taker_fee=self.taker_fee,
                slippage_rate=self.slippage_rate,
            )
            decision_record['actual_reward_risk'] = actual_reward_risk
            if actual_reward_risk is None or actual_reward_risk < MIN_REWARD_RISK:
                self._record_open_invalidation(
                    decision_record,
                    entry_index=entry_index,
                    reason='下一根开盘后结构价格次序或成本后收益风险比失效，未开仓',
                )
                return
        decision_record['entry_status'] = 'OPENED'
        self.decisions.append(decision_record)
        self.pending_signal = None
        self._open_position(prepared_position)
        if self.state == 'POSITION_OPEN':
            self.step_position()

    def _record_open_invalidation(
        self,
        decision_record: dict[str, object],
        *,
        entry_index: int,
        reason: str,
    ) -> None:
        """Persist a rejected next-open execution without partially opening a trade."""
        decision_record['entry_status'] = 'INVALIDATED_AT_OPEN'
        decision_record['entry_status_reason'] = reason
        self.decisions.append(decision_record)
        self.pending_signal = None
        self.cursor = min(entry_index, len(self.snapshots) - 1)
        self.state = 'RUNNING' if self.cursor < len(self.snapshots) - 1 else 'FINISHED'

    def step_position(self) -> None:
        """Reveal and evaluate exactly one additional candle for an open position."""
        if self.state != 'POSITION_OPEN' or self.active_position is None:
            raise ValueError('replay has no open position to advance')
        position = self.active_position
        next_index = max(self.cursor + 1, position.entry_index)
        if next_index >= len(self.snapshots):
            self.state = 'FINISHED'
            self.active_position = None
            return
        candle = self.snapshots.iloc[next_index]
        self.cursor = next_index
        self._settle_funding_until(candle.opened_at)
        position = self.active_position
        if position is None:
            raise ValueError('replay lost its open position')
        exit_price, exit_reason, exit_at_open = _candle_exit(position, candle)
        if exit_price is None:
            self._settle_funding_until(candle.closed_at)
            position = self.active_position
            if position is None:
                raise ValueError('replay lost its open position')
            if _close_crossed_liquidation(position, candle.close):
                exit_price, exit_reason = candle.close, 'LIQUIDATION'
        if (
            exit_price is None
            and self.maximum_holding_bars is not None
            and next_index >= position.entry_index + self.maximum_holding_bars - 1
        ):
            exit_price, exit_reason = candle.close, 'TIME'
        if exit_price is None and next_index >= len(self.snapshots) - 1:
            exit_price, exit_reason = candle.close, 'FINALIZE'
        if exit_price is not None and exit_reason is not None:
            self._close_position(
                exit_price,
                exit_reason,
                next_index,
                exit_at_open=exit_at_open,
            )

    def _settle_funding_until(self, end: pd.Timestamp) -> None:
        """Apply each local historical funding settlement once while a position is open."""
        position = self.active_position
        if position is None or end <= position.funding_cursor:
            return
        funding = 0.0
        if not self.funding_rates.empty:
            due = self.funding_rates.loc[
                (self.funding_rates.index > position.funding_cursor)
                & (self.funding_rates.index <= end)
            ]
            for settlement_time, rate in due.items():
                reference_price = self._funding_reference_price(settlement_time)
                funding += funding_cash_flow(
                    position.side,
                    position.quantity * reference_price,
                    float(rate),
                )
        self.cash += funding
        liquidation_price = position.liquidation_price
        if position.margin_mode is MarginMode.CROSS:
            liquidation_price = _liquidation_price(
                side=position.side,
                fill_price=position.fill_price,
                quantity=position.quantity,
                opening_amount=self.opening_amount,
                cash_after_entry_fee=self.cash,
                margin_mode=position.margin_mode,
                maintenance_margin_rate=self.maintenance_margin_rate,
            )
        self.active_position = replace(
            position,
            liquidation_price=liquidation_price,
            risk_warning=_liquidation_warning(
                position.side,
                position.stop_price,
                liquidation_price,
            ),
            funding=position.funding + funding,
            funding_cursor=end,
        )

    def _funding_reference_price(self, settlement_time: pd.Timestamp) -> float:
        """Use the latest completed local 5m close as the unavailable mark-price proxy."""
        frame = self.chart_frames['5m']
        completed = frame.loc[
            (frame.index + pd.Timedelta(minutes=5)) <= settlement_time,
            'Close',
        ]
        if not completed.empty:
            return float(completed.iloc[-1])
        position = self.active_position
        if position is None:
            raise ValueError('replay has no position for funding settlement')
        return position.fill_price

    def continue_after_exit(self) -> None:
        """Leave the exit pause and allow the fast signal scan to resume."""
        if self.state != 'AWAITING_CONTINUE':
            raise ValueError('replay is not waiting to continue')
        self.state = 'RUNNING' if self.cursor < len(self.snapshots) - 1 else 'FINISHED'

    def visible_payload(self) -> dict[str, object]:
        """Expose only the completed replay prefix, never the unseen future suffix."""
        visible_end = min(self.cursor + 1, len(self.snapshots))
        start = max(0, visible_end - 500)
        visible = self.snapshots.iloc[start:visible_end]
        cursor_time = visible.index[-1]
        signal_payload = self._pending_signal_payload() if self.pending_signal else None
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
            'position_overlay': self._position_overlay_payload(),
            'trades': [_trade_payload(trade) for trade in self.trades],
            'equity_curve': [
                {'timestamp': timestamp.isoformat(), 'equity': equity}
                for timestamp, equity in self.equity_points
            ],
            'cursor_time': cursor_time.isoformat(),
            'decisions': len(self.decisions),
            'replay_stats': self._replay_stats(),
            'last_execution_notice': _last_execution_notice(self.decisions),
            'funding_available': not self.funding_rates.empty,
            'whitelist_profile': self.whitelist_profile,
        }

    def _replay_stats(self) -> dict[str, object]:
        """Return durable human-review progress and realized results."""
        total_candidates = (
            int(len(self.candidate_features))
            if self.candidate_features is not None
            else None
        )
        tested = len(self.decisions)
        opened = sum(item.get('entry_status') == 'OPENED' for item in self.decisions)
        skipped = sum(item.get('entry_status') == 'SKIPPED' for item in self.decisions)
        invalidated = sum(
            item.get('entry_status') == 'INVALIDATED_AT_OPEN'
            for item in self.decisions
        )
        wins = sum(trade.pnl > 0 for trade in self.trades)
        losses = sum(trade.pnl <= 0 for trade in self.trades)
        completed = wins + losses
        cumulative_pnl = sum(trade.pnl for trade in self.trades)
        return {
            'tested': tested,
            'total_candidates': total_candidates,
            'opened': opened,
            'skipped': skipped,
            'invalidated': invalidated,
            'wins': wins,
            'losses': losses,
            'win_rate': wins / completed if completed else None,
            'cumulative_net_pnl': cumulative_pnl,
            'current_equity': self.cash,
        }

    def _pending_signal_payload(self) -> dict[str, object]:
        signal = self.pending_signal
        if signal is None:
            raise ValueError('replay has no pending signal')
        fill_price = _adverse_fill(signal.side, signal.signal_close, self.slippage_rate)
        quantity = self.opening_amount * self.leverage / fill_price
        entry_fee = self.opening_amount * self.leverage * self.taker_fee
        liquidation_price = _liquidation_price(
            side=signal.side,
            fill_price=fill_price,
            quantity=quantity,
            opening_amount=self.opening_amount,
            cash_after_entry_fee=self.cash - entry_fee,
            margin_mode=self.margin_mode,
            maintenance_margin_rate=self.maintenance_margin_rate,
        )
        stop_price, _ = _resolve_risk_prices(signal, signal.side, fill_price)
        payload = _signal_payload(signal, self.timeframe)
        payload.update({
            'estimated_liquidation_price': liquidation_price,
            'margin_mode': self.margin_mode.value,
            'margin_mode_label': MARGIN_MODE_LABELS[self.margin_mode],
            'risk_warning': _liquidation_warning(signal.side, stop_price, liquidation_price),
        })
        return payload

    def persist(self, root: Path) -> Path:
        """Persist only decisions and completed trades as a reproducible local artifact."""
        destination = root / f'{self.session_id}.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self.visible_payload()
        payload['trades'] = [asdict(trade) for trade in self.trades]
        destination.write_text(json.dumps(payload, default=str, ensure_ascii=False, indent=2), encoding='utf-8')
        return destination

    def _prepare_position(
        self,
        signal: Signal,
        decision: Literal['BUY', 'SELL'],
        entry_index: int,
    ) -> ActivePosition:
        """Build and validate every execution level before replay state is mutated."""
        entry = self.snapshots.iloc[entry_index]
        fill_price = _adverse_fill(decision, entry.open, self.slippage_rate)
        stop_price, target_price = _resolve_risk_prices(signal, decision, fill_price)
        quantity = self.opening_amount * self.leverage / fill_price
        entry_fee = self.opening_amount * self.leverage * self.taker_fee
        liquidation_price = _liquidation_price(
            side=decision,
            fill_price=fill_price,
            quantity=quantity,
            opening_amount=self.opening_amount,
            cash_after_entry_fee=self.cash - entry_fee,
            margin_mode=self.margin_mode,
            maintenance_margin_rate=self.maintenance_margin_rate,
        )
        return ActivePosition(
            signal_time=signal.signal_time,
            side=decision,
            entry_index=entry_index,
            fill_time=entry.opened_at,
            fill_price=fill_price,
            stop_price=stop_price,
            target_price=target_price,
            liquidation_price=liquidation_price,
            margin_mode=self.margin_mode,
            risk_warning=_liquidation_warning(decision, stop_price, liquidation_price),
            quantity=quantity,
            entry_fee=entry_fee,
            funding=0.0,
            funding_cursor=entry.opened_at,
        )

    def _open_position(self, position: ActivePosition) -> None:
        """Atomically activate a position whose entry plan has already been validated."""
        self.cash -= position.entry_fee
        self.active_position = position
        self.state = 'POSITION_OPEN'

    def _close_position(
        self,
        exit_price: float,
        exit_reason: ExitReason,
        exit_index: int,
        *,
        exit_at_open: bool = False,
    ) -> None:
        position = self.active_position
        if position is None:
            raise ValueError('replay has no open position to close')
        exit_price = _adverse_fill(
            'SELL' if position.side == 'BUY' else 'BUY',
            exit_price,
            self.slippage_rate,
        )
        direction = 1 if position.side == 'BUY' else -1
        gross = position.quantity * (exit_price - position.fill_price) * direction
        exit_fee_rate = self.liquidation_fee_rate if exit_reason == 'LIQUIDATION' else self.taker_fee
        exit_fee = position.quantity * exit_price * exit_fee_rate
        self.cash += gross - exit_fee
        exit_snapshot = self.snapshots.iloc[exit_index]
        trade = ManualTrade(
            signal_time=position.signal_time,
            side=position.side,
            fill_time=position.fill_time,
            fill_price=position.fill_price,
            stop_price=position.stop_price,
            target_price=position.target_price,
            liquidation_price=position.liquidation_price,
            margin_mode=position.margin_mode,
            exit_time=(
                exit_snapshot.opened_at
                if exit_at_open
                else exit_snapshot.closed_at
            ),
            exit_price=exit_price,
            exit_reason=exit_reason,
            liquidation_fee=exit_fee if exit_reason == 'LIQUIDATION' else 0.0,
            funding=position.funding,
            pnl=gross - position.entry_fee - exit_fee + position.funding,
            equity=self.cash,
        )
        self.trades.append(trade)
        self.equity_points.append((trade.exit_time, self.cash))
        self.cursor = exit_index
        self.active_position = None
        self.state = 'AWAITING_CONTINUE'

    def _position_overlay_payload(self) -> dict[str, object] | None:
        if self.active_position is not None:
            position = self.active_position
            current = self.snapshots.iloc[self.cursor]
            return {
                'status': 'OPEN',
                'side': position.side,
                'entry_time': int(position.fill_time.timestamp()),
                'end_time': int(current.opened_at.timestamp()),
                'fill_price': position.fill_price,
                'stop_price': position.stop_price,
                'target_price': position.target_price,
                'liquidation_price': position.liquidation_price,
                'margin_mode': position.margin_mode.value,
                'margin_mode_label': MARGIN_MODE_LABELS[position.margin_mode],
                'risk_warning': position.risk_warning,
                'leverage': self.leverage,
                'funding': position.funding,
                'time_exit_at': self._time_exit_at(position),
                'remaining_holding_bars': self._remaining_holding_bars(position),
            }
        if self.state == 'AWAITING_CONTINUE' and self.trades:
            trade = self.trades[-1]
            return {
                'status': 'CLOSED',
                'side': trade.side,
                'entry_time': int(trade.fill_time.timestamp()),
                'end_time': int(trade.exit_time.timestamp()) - SIGNAL_TIMEFRAME_SECONDS[self.timeframe],
                'fill_price': trade.fill_price,
                'stop_price': trade.stop_price,
                'target_price': trade.target_price,
                'liquidation_price': trade.liquidation_price,
                'margin_mode': trade.margin_mode.value,
                'margin_mode_label': MARGIN_MODE_LABELS[trade.margin_mode],
                'exit_price': trade.exit_price,
                'exit_reason': trade.exit_reason,
                'exit_reason_label': EXIT_REASON_LABELS[trade.exit_reason],
                'leverage': self.leverage,
                'funding': trade.funding,
            }
        return None

    def _time_exit_at(self, position: ActivePosition) -> str | None:
        if self.maximum_holding_bars is None:
            return None
        exit_index = min(
            len(self.snapshots) - 1,
            position.entry_index + self.maximum_holding_bars - 1,
        )
        return self.snapshots.iloc[exit_index].closed_at.isoformat()

    def _remaining_holding_bars(self, position: ActivePosition) -> int | None:
        if self.maximum_holding_bars is None:
            return None
        exit_index = position.entry_index + self.maximum_holding_bars - 1
        return max(0, exit_index - self.cursor)


def _liquidation_price(
    *,
    side: Literal['BUY', 'SELL'],
    fill_price: float,
    quantity: float,
    opening_amount: float,
    cash_after_entry_fee: float,
    margin_mode: MarginMode,
    maintenance_margin_rate: float,
) -> float:
    collateral = opening_amount if margin_mode is MarginMode.ISOLATED else max(0.0, cash_after_entry_fee)
    return estimate_position_liquidation_price(
        side=side,
        entry_price=fill_price,
        quantity=quantity,
        collateral=collateral,
        maintenance_margin_rate=maintenance_margin_rate,
    )


def _liquidation_warning(
    side: Literal['BUY', 'SELL'],
    stop_price: float,
    liquidation_price: float,
) -> str | None:
    stop_beyond_liquidation = (
        side == 'BUY' and stop_price <= liquidation_price
    ) or (
        side == 'SELL' and stop_price >= liquidation_price
    )
    if not stop_beyond_liquidation:
        return None
    return '当前止损位在估算强平价之外，价格会先触发强平；请降低杠杆或缩短止损距离'


def _close_crossed_liquidation(position: ActivePosition, close: float) -> bool:
    if position.margin_mode is not MarginMode.CROSS:
        return False
    if position.side == 'BUY':
        return close <= position.liquidation_price
    return close >= position.liquidation_price


def _candle_exit(
    position: ActivePosition,
    candle: MarketSnapshot,
) -> tuple[float | None, ExitReason | None, bool]:
    if position.side == 'BUY':
        if candle.open <= position.liquidation_price:
            return candle.open, 'LIQUIDATION', True
        if position.stop_price > position.liquidation_price:
            if candle.open <= position.stop_price:
                return candle.open, 'STOP', True
        if candle.open >= position.target_price:
            return position.target_price, 'TARGET', True
        if position.stop_price > position.liquidation_price:
            if candle.low <= position.stop_price:
                return position.stop_price, 'STOP', False
        elif candle.low <= position.liquidation_price:
            return position.liquidation_price, 'LIQUIDATION', False
        if candle.high >= position.target_price:
            return position.target_price, 'TARGET', False
        return None, None, False
    if candle.open >= position.liquidation_price:
        return candle.open, 'LIQUIDATION', True
    if position.stop_price < position.liquidation_price:
        if candle.open >= position.stop_price:
            return candle.open, 'STOP', True
    if candle.open <= position.target_price:
        return position.target_price, 'TARGET', True
    if position.stop_price < position.liquidation_price:
        if candle.high >= position.stop_price:
            return position.stop_price, 'STOP', False
    elif candle.high >= position.liquidation_price:
        return position.liquidation_price, 'LIQUIDATION', False
    if candle.low <= position.target_price:
        return position.target_price, 'TARGET', False
    return None, None, False


def _adverse_fill(side: Literal['BUY', 'SELL'], price: float, slippage: float) -> float:
    return price * (1 + slippage if side == 'BUY' else 1 - slippage)


def _resolve_risk_prices(
    signal: Signal,
    decision: Literal['BUY', 'SELL'],
    fill_price: float,
) -> tuple[float, float]:
    structural = signal.structural_risk
    if structural is not None:
        if decision != signal.side:
            raise ValueError('关键区域候选不能反向使用冻结结构价格')
        stop_price = structural.stop_price
        target_price = structural.target_price
    else:
        direction = 1 if decision == 'BUY' else -1
        stop_price = fill_price - direction * signal.stop_distance
        target_price = fill_price + direction * signal.target_distance
    correctly_ordered = (
        stop_price < fill_price < target_price
        if decision == 'BUY'
        else target_price < fill_price < stop_price
    )
    if not correctly_ordered:
        raise ValueError('成交价已越过冻结的止损或止盈价格')
    return stop_price, target_price


def _normalize_funding_rates(rates: pd.Series) -> pd.Series:
    """Align exchange millisecond jitter to the actual settlement minute."""
    if not isinstance(rates.index, pd.DatetimeIndex):
        raise ValueError('funding rate index must be a DatetimeIndex')
    normalized = rates.copy()
    if normalized.index.tz is None:
        normalized.index = normalized.index.tz_localize('UTC')
    else:
        normalized.index = normalized.index.tz_convert('UTC')
    normalized.index = normalized.index.floor('min')
    if normalized.index.has_duplicates:
        normalized = normalized.groupby(level=0).last()
    return normalized.sort_index().astype(float)


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
    payload: dict[str, object] = {
        'time': _signal_candle_time(signal, timeframe),
        'mode': signal.mode.value,
        'side': signal.side,
        'reason': _display_reason(signal.reason),
        'score': signal.score,
        'summary': _signal_summary(signal.side),
    }
    if signal.structural_risk is not None:
        payload.update({
            'risk_model': 'STRUCTURAL_ZONE',
            'stop_price': signal.structural_risk.stop_price,
            'target_price': signal.structural_risk.target_price,
            'entry_zone_lower': signal.structural_risk.entry_zone_lower,
            'entry_zone_upper': signal.structural_risk.entry_zone_upper,
            'target_zone_lower': signal.structural_risk.target_zone_lower,
            'target_zone_upper': signal.structural_risk.target_zone_upper,
            'reward_risk': signal.structural_risk.reference_reward_risk,
            'reference_reward_risk': signal.structural_risk.reference_reward_risk,
        })
    else:
        payload['risk_model'] = 'ATR_DISTANCE'
        payload['stop_price'] = signal.estimated_stop_price
        payload['target_price'] = signal.estimated_target_price
        payload['reward_risk'] = signal.target_distance / signal.stop_distance
    return payload


def _last_execution_notice(
    decisions: list[dict[str, object]],
) -> dict[str, object] | None:
    if not decisions:
        return None
    latest = decisions[-1]
    if latest.get('entry_status') != 'INVALIDATED_AT_OPEN':
        return None
    return {
        'status': 'INVALIDATED_AT_OPEN',
        'summary': '上一候选开盘失效，未开仓',
        'reason': latest.get('entry_status_reason', '下一根开盘不再满足执行条件'),
        'time': latest.get('time'),
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
        'stop_price': trade.stop_price,
        'target_price': trade.target_price,
        'liquidation_price': trade.liquidation_price,
        'margin_mode': trade.margin_mode.value,
        'margin_mode_label': MARGIN_MODE_LABELS[trade.margin_mode],
        'exit_time': trade.exit_time.isoformat(),
        'exit_price': trade.exit_price,
        'exit_reason': trade.exit_reason,
        'exit_reason_label': EXIT_REASON_LABELS[trade.exit_reason],
        'liquidation_fee': trade.liquidation_fee,
        'funding': trade.funding,
        'pnl': trade.pnl,
        'equity': trade.equity,
    }
