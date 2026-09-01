"""ScoreBar 相似度分数条测试。"""

from gui.widgets.score_bar import ScoreBar


def test_construction_default_score():
    bar = ScoreBar()
    assert bar.score() == 0.0


def test_construction_with_score():
    bar = ScoreBar(score=0.85)
    assert abs(bar.score() - 0.85) < 1e-9


def test_set_score_updates_value():
    bar = ScoreBar()
    bar.set_score(0.42)
    assert abs(bar.score() - 0.42) < 1e-9


def test_set_score_clamps_range():
    bar = ScoreBar()
    bar.set_score(1.7)
    assert bar.score() == 1.0
    bar.set_score(-0.3)
    assert bar.score() == 0.0


def test_score_text_shows_percentage():
    bar = ScoreBar()
    bar.set_score(0.856)
    assert "86" in bar._score_label.text() or "85" in bar._score_label.text()


def test_bar_widget_exists():
    bar = ScoreBar()
    assert bar._bar is not None
