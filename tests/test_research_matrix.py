from __future__ import annotations

import pandas as pd
import pytest

from scripts.research_event_factors import (
    _RESEARCH_MATRIX_SPECS,
    build_research_matrix,
    write_research_matrix_report,
)


def test_matrix_pools_frozen_source_slices_with_fixed_cost(tmp_path) -> None:
    index = pd.DatetimeIndex(
        ['2025-01-01T01:00:00Z', '2025-01-02T01:00:00Z'],
        name='event_time',
    )
    for _, horizon, _, filenames in _RESEARCH_MATRIX_SPECS:
        for filename in filenames:
            pd.DataFrame(
                {f'forward_return_{horizon}': [0.002, 0.002]},
                index=index,
            ).to_csv(tmp_path / filename)

    rows = build_research_matrix(results_root=tmp_path)

    assert len(rows) == len(_RESEARCH_MATRIX_SPECS)
    for row in rows:
        assert row.status == 'COMPLETE'
        assert row.metrics.average_gross_return == pytest.approx(0.002)
        assert row.metrics.average_net_return == pytest.approx(0.0006)
        assert row.metrics.break_even_round_trip_cost == pytest.approx(0.002)
        assert row.metrics.net_mean_ci_lower == pytest.approx(0.0006)


def test_matrix_report_explains_break_even_cost(tmp_path) -> None:
    index = pd.DatetimeIndex(
        ['2025-01-01T01:00:00Z', '2025-01-02T01:00:00Z'],
        name='event_time',
    )
    for _, horizon, _, filenames in _RESEARCH_MATRIX_SPECS:
        for filename in filenames:
            pd.DataFrame(
                {f'forward_return_{horizon}': [0.002, 0.002]},
                index=index,
            ).to_csv(tmp_path / filename)
    output = tmp_path / 'matrix.md'

    write_research_matrix_report(build_research_matrix(results_root=tmp_path), output)

    report = output.read_text(encoding='utf-8')
    assert 'Break-even cost equals the average gross return' in report
    assert 'Net mean 95% CI %' in report
    assert 'A large event count alone is not evidence of edge.' in report
