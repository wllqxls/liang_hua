"""Scan the non-frozen 2025 order-flow grid as exploration only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.semi_auto_optimizer import (  # noqa: E402
    explore_2025_parameter_grid,
    write_grid_exploration,
)


FROZEN_BTC_PROFILE = (0.575, 0.002, '4h')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='2025 parameter-grid exploration; never promotes strategies',
    )
    parser.add_argument('--symbol', default='BTC/USDT', choices=('BTC/USDT', 'ETH/USDT'))
    parser.add_argument(
        '--output',
        type=Path,
        default=PROJECT_ROOT / 'results' / 'semi_auto_2025_grid_exploration.csv',
    )
    args = parser.parse_args()
    excluded = FROZEN_BTC_PROFILE if args.symbol == 'BTC/USDT' else None
    rows = explore_2025_parameter_grid(
        PROJECT_ROOT / 'data',
        symbol=args.symbol,
        excluded_profile=excluded,
    )
    write_grid_exploration(rows, args.output)
    passing = sum(item.passes_numeric_gate for item in rows)
    print(f'wrote {len(rows)} exploration rows to {args.output}')
    print(f'numeric-gate rows: {passing}; status remains EXPLORATION_ONLY')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
