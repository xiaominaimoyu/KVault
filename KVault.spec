"""KVault PyInstaller spec — corrected and hardened.

Key fixes vs. previous version:
  * Replaced PyPDF2 → fitz (PyMuPDF is the actual PDF library)
  * Fixed python-docx → docx, python-pptx → pptx (real import names)
  * Added collect_all() for chromadb, PySide6, fitz, mcp, docx, pptx
  * Added missing hidden imports for langchain, ollama, httpx, etc.
  * Switched to onedir mode for reliable ChromaDB / SQLite operation
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

sys.setrecursionlimit(sys.getrecursionlimit() * 2)

# SPECPATH is injected by PyInstaller — directory containing this .spec file
_spec_dir = os.environ.get("SPECPATH", os.getcwd())

block_cipher = None

# ── accumulate datas / binaries / hidden-imports ──────────────────
all_datas = [("config.json.example", ".")]
all_binaries: list = []
all_hidden: list = []

# Complex packages: collect everything (submodules + data + native libs)
_collect_pkgs = [
    "chromadb",
    "PySide6",
    "fitz",
    "mcp",
    "docx",
    "pptx",
    "openpyxl",
    "ollama",
    "langchain_text_splitters",
]

for _pkg in _collect_pkgs:
    try:
        _d, _b, _h = collect_all(_pkg)
        all_datas += _d
        all_binaries += _b
        all_hidden += _h
    except Exception:
        pass  # package not installed — skip gracefully

# Extra hidden imports that collect_all might miss
_extra_hidden = [
    # stdlib / utility
    "sqlite3",
    "cffi",
    "cryptography",
    "pydantic",
    "click",
    "tqdm",
    "requests",
    "urllib3",
    "idna",
    "certifi",
    "charset_normalizer",
    "packaging",
    "filetype",
    # networking (mcp deps)
    "httpx",
    "starlette",
    "anyio",
    "h11",
    "sniffio",
    "sse_starlette",
    # langchain ecosystem
    "langchain",
    "langchain_core",
    "langchain_community",
    # PySide6 extra modules
    "PySide6.QtNetwork",
    "PySide6.QtPrintSupport",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtXml",
    # document parsing deps
    "lxml",
    "lxml._elementpath",
    "PIL",
    "PIL._tkinter_finder",
]

a = Analysis(
    ["main.py"],
    pathex=[_spec_dir],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden + _extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "scipy",
        "pandas",
        "pytest",
        "IPython",
        "notebook",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KVault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="KVault",
)
