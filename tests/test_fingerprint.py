from __future__ import annotations

from pathlib import Path

import pytest

from core.fingerprint import Fingerprint, FingerprintError


def test_fingerprint_stability(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("hello world", encoding="utf-8")
    fp1 = Fingerprint.compute(p)
    fp2 = Fingerprint.compute(p)
    assert fp1.content_hash == fp2.content_hash
    assert fp1.size == fp2.size


def test_fingerprint_changes_on_content(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("content A", encoding="utf-8")
    fp1 = Fingerprint.compute(p)
    p.write_text("content B", encoding="utf-8")
    fp2 = Fingerprint.compute(p)
    assert fp1.content_hash != fp2.content_hash


def test_fingerprint_nonexistent(tmp_path: Path):
    with pytest.raises(FingerprintError):
        Fingerprint.compute(tmp_path / "nope.txt")