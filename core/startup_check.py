import logging
from dataclasses import dataclass

import ollama

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    suggestion: str = ""


class StartupChecker:
    def __init__(self, config):
        self.config = config

    def check_all(self) -> list[CheckResult]:
        results = []
        results.append(self._check_data_dirs())
        results.append(self._check_sqlite())
        results.append(self._check_ollama_service())
        results.append(self._check_embedding_model())
        return results

    def _check_data_dirs(self) -> CheckResult:
        dirs = [
            self.config.files_dir,
            self.config.chroma_dir,
            self.config.sqlite_path.parent,
            self.config.logs_dir,
        ]
        try:
            for d in dirs:
                d.mkdir(parents=True, exist_ok=True)
            return CheckResult(
                name="数据目录",
                passed=True,
                message="所有数据目录已创建",
            )
        except Exception as e:
            return CheckResult(
                name="数据目录",
                passed=False,
                message=f"创建数据目录失败: {e}",
                suggestion="请检查目录权限",
            )

    def _check_sqlite(self) -> CheckResult:
        import sqlite3

        try:
            conn = sqlite3.connect(
                str(self.config.sqlite_path), check_same_thread=False
            )
            conn.execute("SELECT 1")
            conn.close()
            return CheckResult(
                name="SQLite",
                passed=True,
                message="SQLite 连接正常",
            )
        except Exception as e:
            return CheckResult(
                name="SQLite",
                passed=False,
                message=f"SQLite 连接失败: {e}",
                suggestion="请检查数据库路径权限",
            )

    def _check_ollama_service(self) -> CheckResult:
        try:
            client = ollama.Client(host=self.config.ollama_base_url)
            client.list()
            return CheckResult(
                name="Ollama 服务",
                passed=True,
                message="Ollama 服务正常运行",
            )
        except Exception as e:
            return CheckResult(
                name="Ollama 服务",
                passed=False,
                message=f"无法连接 Ollama 服务: {e}",
                suggestion="请启动 Ollama 服务: `ollama serve`",
            )

    def _check_embedding_model(self) -> CheckResult:
        try:
            client = ollama.Client(host=self.config.ollama_base_url)
            models = client.list().get("models", [])
            names = {m.get("model", "") for m in models}
            target = self.config.embedding_model
            if target in names:
                return CheckResult(
                    name="嵌入模型",
                    passed=True,
                    message=f"模型 {target} 已就绪",
                )
            for name in names:
                if target in name or name.endswith(f":{target}"):
                    return CheckResult(
                        name="嵌入模型",
                        passed=True,
                        message=f"模型 {name} 已就绪",
                    )
            return CheckResult(
                name="嵌入模型",
                passed=False,
                message=f"模型 {target} 未找到",
                suggestion=f"请拉取模型: `ollama pull {target}`",
            )
        except Exception as e:
            return CheckResult(
                name="嵌入模型",
                passed=False,
                message=f"检查模型失败: {e}",
                suggestion="请确保 Ollama 服务已启动",
            )

    def has_errors(self, results: list[CheckResult]) -> bool:
        return any(not r.passed for r in results)