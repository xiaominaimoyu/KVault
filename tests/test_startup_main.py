from pathlib import Path

import main as main_mod
from core.startup_check import CheckResult, StartupChecker


def test_main_creates_qapp_before_capability_probe():
    """QApplication 必须先于能力探测创建（探测可能触发 UI 刷新）。"""
    src = Path(main_mod.__file__).read_text(encoding="utf-8")
    main_fn = src[src.index("def main("):]
    qapp_pos = main_fn.index("QApplication(sys.argv)")
    probe_pos = main_fn.index("probe(config)")
    assert qapp_pos < probe_pos


def test_main_does_not_block_on_capability_probe():
    """无本地模型时程序必须正常启动，不得弹阻塞式模态框。

    回归防护：曾经存在 StartupDialog.exec() 阻塞门禁，
    导致没有 Ollama 的用户每次启动都必须手动点「跳过」。
    """
    src = Path(main_mod.__file__).read_text(encoding="utf-8")
    main_fn = src[src.index("def main("):]
    assert "StartupDialog" not in main_fn
    assert "_run_startup_check" not in main_fn


def test_main_passes_capabilities_to_window():
    src = Path(main_mod.__file__).read_text(encoding="utf-8")
    assert "capabilities=capabilities" in src


def test_startup_checker_data_dirs(tmp_config):
    checker = StartupChecker(tmp_config)
    results = checker.check_all()
    assert len(results) == 4
    assert any(r.name for r in results)


def test_startup_checker_llama_cpp_branch_skips_ollama(tmp_config, monkeypatch):
    """选择 llama.cpp 后端时不应去连 Ollama 服务。"""
    tmp_config.embedding_backend = "llama_cpp"

    def boom(*args, **kwargs):
        raise AssertionError("llama.cpp 后端不应访问 Ollama")

    monkeypatch.setattr("ollama.Client", boom)
    checker = StartupChecker(tmp_config)
    results = checker.check_all()
    names = {r.name for r in results}
    assert "llama.cpp 依赖" in names
    assert "GGUF 模型" in names
    assert "Ollama 服务" not in names
    assert "嵌入模型" not in names


def test_check_result_carries_suggestion():
    r = CheckResult("n", False, "m", "s")
    assert r.suggestion == "s"