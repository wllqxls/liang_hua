# Four-Column Form Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the main and advanced backtest parameter grids display four columns on desktop, two on medium screens, and one on narrow screens.

**Architecture:** Keep the existing shared `.form-grid` class and replace its automatic column calculation with an explicit four-column grid. Add two media queries so both the main form and `.advanced-grid` inherit the same responsive behavior without HTML or JavaScript changes.

**Tech Stack:** HTML templates, CSS Grid, Python `pytest`

---

### Task 1: Lock and implement the responsive form grid

**Files:**
- Create: `tests/test_styles.py`
- Modify: `static/css/style.css:175`

- [ ] **Step 1: Write the failing style contract test**

```python
from pathlib import Path


STYLE_PATH = Path(__file__).parents[1] / 'static' / 'css' / 'style.css'


def test_form_grid_has_explicit_responsive_columns() -> None:
    css = STYLE_PATH.read_text(encoding='utf-8')

    assert 'grid-template-columns: repeat(4, minmax(0, 1fr));' in css
    assert '@media (max-width: 800px)' in css
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr));' in css
    assert '@media (max-width: 520px)' in css
    assert 'grid-template-columns: minmax(0, 1fr);' in css
```

- [ ] **Step 2: Run the new test and verify the current CSS fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_styles.py -q
```

Expected: `FAIL` because the current CSS contains `repeat(auto-fill, minmax(180px, 1fr))` and has no responsive form-grid breakpoints.

- [ ] **Step 3: Implement the minimum CSS change**

Replace the `.form-grid` column declaration with:

```css
.form-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin-bottom: 20px;
}
```

Add these rules after the form control styles:

```css
@media (max-width: 800px) {
    .form-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 520px) {
    .form-grid {
        grid-template-columns: minmax(0, 1fr);
    }
}
```

- [ ] **Step 4: Run the focused and full test suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_styles.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: the focused test passes and all project tests pass.

- [ ] **Step 5: Verify the live service and hand off browser refresh**

Run:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

Expected: one listener on `127.0.0.1:8000`. The user can refresh the already-open browser tab to load the updated stylesheet.

- [ ] **Step 6: Commit only the layout implementation**

```powershell
git add tests/test_styles.py static/css/style.css
git commit -m "Fix responsive form grid layout"
```

Do not stage the pre-existing `requirements.txt` change.
