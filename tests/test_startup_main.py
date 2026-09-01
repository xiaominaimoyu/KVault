from pathlib import Path

import main as main_mod
from core.startup_check import StartupChecker, CheckResult


def test_main_creates_qapp_before_startup_dialog():
    src = Path(main_mod.__file__).read_text(encoding="utf-8")
    main_fn = src[src.index("def main("):]
    qapp_pos = main_fn.index("QApplication(sys.argv)")
    check_pos = main_fn.index("_run_startup_check(")
    assert qapp_pos < check_pos


def test_run_startup_check_retries_on_accept(monkeypatch, tmp_config):
    calls = {"n": 0}

    class FakeDialog:
        Accepted = 1
        Rejected = 0

        def __init__(self, results, parent=None):
            pass

        def exec(self):
            calls["n"] += 1
            return FakeDialog.Accepted

    class FakeChecker:
        def __init__(self, config):
            self.config = config
            self._i = 0

        def check_all(self):
            self._i += 1
            if self._i == 1:
                return [CheckResult("x", False, "fail", "fix")]
            return [CheckResult("x", True, "ok")]

        def has_errors(self, results):
            return any(not r.passed for r in results)

    monkeypatch.setattr(main_mod, "StartupChecker", FakeChecker)
    monkeypatch.setattr(main_mod, "StartupDialog", FakeDialog)
    assert main_mod._run_startup_check(tmp_config) is True
    assert calls["n"] == 1


def test_startup_checker_data_dirs(tmp_config):
    checker = StartupChecker(tmp_config)
    results = checker.check_all()
    assert len(results) == 4
    assert any(r.name for r in results)
