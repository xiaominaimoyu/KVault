"""StepIndicator 步骤指示器测试。"""

from gui.widgets.step_indicator import StepIndicator

STEPS = ["下载模型", "校验文件", "切换版本"]


def test_construction_builds_labels():
    ind = StepIndicator(STEPS)
    assert len(ind._step_labels) == 3
    assert [lbl.text() for lbl in ind._step_labels] == STEPS


def test_default_current_step_is_zero():
    ind = StepIndicator(STEPS)
    assert ind.current_step() == 0


def test_set_current_step():
    ind = StepIndicator(STEPS)
    ind.set_current_step(2)
    assert ind.current_step() == 2


def test_set_current_step_clamped():
    ind = StepIndicator(STEPS)
    ind.set_current_step(5)
    assert ind.current_step() == 2
    ind.set_current_step(-1)
    assert ind.current_step() == 0


def test_completed_steps_before_current():
    ind = StepIndicator(STEPS)
    ind.set_current_step(2)
    # 前两步应被标记为完成
    assert ind.is_completed(0)
    assert ind.is_completed(1)
    assert not ind.is_completed(2)
