"""可选依赖探测模块。

探测 pdfplumber / RapidOCR / jieba 等可选依赖的可用性，
缺失时优雅降级并给出明确提示。
"""

from __future__ import annotations

import importlib.util


class OptionalDepDetector:
    """静态探测可选依赖的可用性。"""

    @staticmethod
    def has_pdfplumber() -> bool:
        return importlib.util.find_spec("pdfplumber") is not None

    @staticmethod
    def has_rapidocr() -> bool:
        return importlib.util.find_spec("rapidocr_onnxruntime") is not None

    @staticmethod
    def has_jieba() -> bool:
        return importlib.util.find_spec("jieba") is not None

    @staticmethod
    def report() -> dict[str, bool]:
        return {
            "pdfplumber": OptionalDepDetector.has_pdfplumber(),
            "rapidocr": OptionalDepDetector.has_rapidocr(),
            "jieba": OptionalDepDetector.has_jieba(),
        }