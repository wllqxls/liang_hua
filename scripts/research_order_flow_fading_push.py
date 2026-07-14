"""Run the frozen fading-push short-reversal study."""

from __future__ import annotations

import argparse
import logging
import math
import subprocess
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research.order_flow_fading_push import (
    FadingPushResearchSlice,
    primary_validation_passed,
    run_fading_push_research,
)


DEFAULT_DATA_ROOT = PROJECT_ROOT / 'data' / 'order_flow' / 'binance_um'
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / 'results' / 'research' / 'order_flow'
DEFAULT_REPORT = PROJECT_ROOT / 'docs' / 'research' / 'order-flow-fading-push-reversal-report.md'
logger = logging.getLogger(__name__)


def write_report(slices: Sequence[FadingPushResearchSlice], output_path: Path) -> None:
    """Write a reproducible report and the frozen 2025 verdict."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# 主动资金退潮后的短期回调研究报告', '',
        '- 状态：只读因子研究；不是策略回测、模拟盘或实盘建议。',
        '- 设计：`docs/research/order-flow-fading-push-reversal-design.md`。',
        '- 数据：2024 用于实现和描述，2025 是独立验证；2026 未读取。',
        '- 成本：完整往返 `0.0014`；30m 是唯一主检验窗口。',
        f'- 代码版本：`{_git_revision()}`。', '',
        '## 事件与数据排除', '',
        '| 标的 | 年份 | 冷却后事件数 | 冷却前合格行 | 因 OI 缺口排除行 | 事件 CSV |',
        '|---|---:|---:|---:|---:|---|',
    ]
    for item in slices:
        lines.append(
            f'| {item.symbol} | {item.year} | {item.events} | {item.eligible_rows} | '
            f'{item.excluded_metric_rows} | `{item.dataset_path.relative_to(PROJECT_ROOT)}` |'
        )
    for item in slices:
        lines.extend(_slice_lines(item))
    verdict = '通过，可提出下一步候选策略设计' if primary_validation_passed(slices) else '未通过；不得进入候选策略或回测调参'
    lines.extend([
        '## 预先声明的 2025 验证门槛', '',
        '- 条件：BTCUSDT、ETHUSDT 均在 30m 总体桶达到样本数 >= 200、平均成本后收益 > 0、Profit Factor >= 1.15。',
        f'- 结果：`{verdict}`。',
        '- 任一细分桶样本不足 200 时仅作描述，不形成策略结论。', '',
    ])
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def _slice_lines(item: FadingPushResearchSlice) -> list[str]:
    lines = [
        f'## {item.symbol} {item.year}', '',
        '| 窗口 | 分组 | 桶 | 样本 | 平均毛收益 | 平均成本后收益 | 胜率 | PF | 样本达标 |',
        '|---|---|---|---:|---:|---:|---:|---:|---|',
    ]
    if item.summary.empty:
        lines.append('| N/A | N/A | N/A | 0 | N/A | N/A | N/A | N/A | no |')
    else:
        for _, row in item.summary.iterrows():
            lines.append(
                f'| {row["horizon"]} | {row["factor"]} | {row["bucket"]} | {int(row["samples"])} | '
                f'{float(row["average_gross_return"]):.6f} | {float(row["average_net_return"]):.6f} | '
                f'{float(row["win_rate_pct"]):.2f}% | {_format_pf(float(row["profit_factor"]))} | '
                f'{"yes" if bool(row["meets_minimum_sample"]) else "no"} |'
            )
    lines.append('')
    return lines


def _format_pf(value: float) -> str:
    return 'N/A' if math.isnan(value) else ('∞' if math.isinf(value) else f'{value:.3f}')


def _git_revision() -> str:
    try:
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=PROJECT_ROOT, capture_output=True, check=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return 'unavailable'
    return result.stdout.strip() or 'unavailable'


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run frozen fading-push reversal research.')
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--report', type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = _parse_args()
    slices = run_fading_push_research(data_root=args.data_root, output_root=args.output_root)
    write_report(slices, args.report)
    logger.info('slices=%s report=%s', len(slices), args.report)


if __name__ == '__main__':
    main()
