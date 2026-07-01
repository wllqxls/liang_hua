from pathlib import Path


STYLE_PATH = Path(__file__).parents[1] / 'static' / 'css' / 'style.css'


def test_form_grid_has_explicit_responsive_columns() -> None:
    css = STYLE_PATH.read_text(encoding='utf-8')

    assert 'grid-template-columns: repeat(4, minmax(0, 1fr));' in css
    assert '@media (max-width: 800px)' in css
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr));' in css
    assert '@media (max-width: 520px)' in css
    assert 'grid-template-columns: minmax(0, 1fr);' in css
