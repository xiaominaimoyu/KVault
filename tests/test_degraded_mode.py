"""受限模式（无本地推理框架）测试。

覆盖三件事：
1. 没有 Ollama / llama.cpp 时，能力探测判定为受限而非崩溃；
2. 受限只影响语义检索与导入，笔记库等功能不受影响；
3. llama.cpp 后端链路（配置 → 工厂 → 服务 → 能力）完整可用。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from core.capabilities import (
    FEATURE_IMPORT,
    FEATURE_SEARCH,
    Capabilities,
    probe,
)
from core.config import Config, LlamaCppConfig
from core.embedding_service import EmbeddingService
from core.startup_check import CheckResult


# --------------------------------------------------------------- 能力探测


def test_probe_without_model_is_limited_not_crashing(tmp_config):
    """核心需求：没有本地推理框架时探测不得抛异常。"""
    caps = probe(tmp_config)
    assert caps.limited is True
    assert caps.embedding_ready is False
    assert caps.reasons, "受限时必须记录原因"
    assert caps.unavailable_features == [FEATURE_SEARCH, FEATURE_IMPORT]


def test_limited_mode_keeps_vault_features(tmp_config):
    """受限模式不得影响笔记库 / 图谱 / 链接 / 关键词检索。"""
    caps = probe(tmp_config)
    available = caps.available_features
    for feature in ("notes", "graph", "links", "keyword_search"):
        assert feature in available


def test_capabilities_message_explains_recovery(tmp_config):
    caps = probe(tmp_config)
    message = caps.user_message()
    assert "受限模式" in message
    assert "语义检索" in message
    assert "重试检测" in message


def test_probe_never_raises_on_broken_checker(tmp_config, monkeypatch):
    """检查器自身崩溃时也必须降级，而不是阻止启动。"""

    def boom(self):
        raise RuntimeError("checker exploded")

    monkeypatch.setattr(
        "core.capabilities.StartupChecker.check_all", boom, raising=True
    )
    caps = probe(tmp_config)
    assert caps.limited is True
    assert caps.reasons


def test_ready_capabilities_report_backend(tmp_config, monkeypatch):
    results = [
        CheckResult("Ollama 服务", True, "ok"),
        CheckResult("嵌入模型", True, "ok"),
    ]
    monkeypatch.setattr(
        "core.capabilities.StartupChecker.check_all", lambda self: results
    )
    caps = probe(tmp_config)
    assert caps.embedding_ready is True
    assert caps.limited is False
    assert caps.unavailable_features == []
    assert FEATURE_SEARCH in caps.available_features


def test_capabilities_dataclass_defaults():
    caps = Capabilities(embedding_ready=False)
    assert caps.limited is True
    assert caps.available_features  # 即使受限也有可用功能


# ------------------------------------------------------------- llama.cpp


@pytest.fixture
def fake_llama_cpp(monkeypatch):
    """注入假的 llama_cpp 模块，模拟已安装的 llama-cpp-python。"""
    module = types.ModuleType("llama_cpp")

    class FakeLlama:
        def __init__(self, model_path, n_gpu_layers=0, n_ctx=2048, embedding=False):
            assert embedding is True, "必须以 embedding 模式加载模型"
            self.model_path = model_path
            self.n_ctx = n_ctx

        def embed(self, text):
            assert text, "不应传入空文本"
            return [0.1, 0.2, 0.3]

    module.Llama = FakeLlama
    monkeypatch.setitem(sys.modules, "llama_cpp", module)
    return module


@pytest.fixture
def llama_config(tmp_config, tmp_path):
    gguf = tmp_path / "embed-model.gguf"
    gguf.write_bytes(b"GGUF")
    tmp_config.embedding_backend = "llama_cpp"
    tmp_config.llama_cpp = LlamaCppConfig(model_path=str(gguf), n_ctx=512)
    return tmp_config


def test_factory_builds_llama_cpp_backend(llama_config):
    svc = EmbeddingService(config=llama_config)
    assert svc.backend_type == "llama_cpp"
    assert svc.model_name == "embed-model.gguf"


def test_llama_cpp_embeds_and_reports_dimension(llama_config, fake_llama_cpp):
    svc = EmbeddingService(config=llama_config)
    assert svc.is_available() is True
    assert svc.is_model_available() is True
    vectors = svc.embed_texts(["a", "b"])
    assert len(vectors) == 2
    assert all(len(v) == 3 for v in vectors)
    assert svc.dimension == 3


def test_llama_cpp_capabilities_ready(llama_config, fake_llama_cpp, monkeypatch):
    """依赖与模型均就绪时，llama.cpp 后端应判定为完整可用。"""
    monkeypatch.setattr(
        "core.capabilities.StartupChecker.check_all",
        lambda self: [
            CheckResult("llama.cpp 依赖", True, "已安装"),
            CheckResult("GGUF 模型", True, "就绪"),
        ],
    )
    caps = probe(llama_config)
    assert caps.embedding_ready is True
    assert caps.backend_type == "llama_cpp"
    assert caps.backend_name == "embed-model.gguf"
    assert FEATURE_IMPORT in caps.available_features


def test_llama_cpp_missing_dependency_is_limited(llama_config, monkeypatch):
    """未安装 llama-cpp-python 时必须判为受限，并给出安装指引。"""
    monkeypatch.setitem(sys.modules, "llama_cpp", None)
    caps = probe(llama_config)
    assert caps.limited is True
    assert any("llama" in r.lower() or "依赖" in r for r in caps.reasons)


def test_llama_cpp_missing_model_is_limited(tmp_config, tmp_path):
    """GGUF 不存在时必须判为受限，而不是崩溃。"""
    tmp_config.embedding_backend = "llama_cpp"
    tmp_config.llama_cpp = LlamaCppConfig(model_path=str(tmp_path / "nope.gguf"))
    caps = probe(tmp_config)
    assert caps.limited is True


def test_mcp_honours_configured_backend(llama_config):
    """MCP 工具必须尊重 embedding_backend，否则会静默降级为 Ollama。"""
    src = Path("mcp_server/tools.py")
    if not src.exists():
        pytest.skip("mcp_server 不可用")
    text = src.read_text(encoding="utf-8")
    assert "config=config" in text


def test_config_rejects_bad_llama_settings(tmp_config):
    tmp_config.embedding_backend = "llama_cpp"
    tmp_config.llama_cpp = LlamaCppConfig(model_path="", n_ctx=1, n_gpu_layers=-1)
    errors = tmp_config.llama_cpp.validate("llama_cpp")
    assert errors, "非法 llama.cpp 配置必须被拒绝"


def test_config_ignores_llama_rules_for_ollama(tmp_config):
    tmp_config.llama_cpp = LlamaCppConfig(model_path="")
    assert tmp_config.llama_cpp.validate("ollama") == []


def test_embedding_service_without_config_defaults_to_ollama():
    svc = EmbeddingService()
    assert svc.backend_type == "ollama"


def test_default_config_backend_is_supported():
    assert Config().embedding_backend in {"ollama", "llama_cpp"}