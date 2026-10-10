"""KVault PyInstaller spec — corrected and hardened.

Key fixes vs. previous version:
  * Replaced PyPDF2 → fitz (PyMuPDF is the actual PDF library)
  * Fixed python-docx → docx, python-pptx → pptx (real import names)
  * Added collect_all() for chromadb, PySide6, fitz, mcp, docx, pptx
  * Added missing hidden imports for langchain, ollama, httpx, etc.
  * Switched to onedir mode for reliable ChromaDB / SQLite operation
  * Bundled gui/styles/** — QSS 与 SVG 图标在运行时按文件路径读取，
    缺失会导致打包后无主题、无图标
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all

sys.setrecursionlimit(sys.getrecursionlimit() * 2)

# SPECPATH is injected by PyInstaller — directory containing this .spec file
_spec_dir = os.environ.get("SPECPATH", os.getcwd())

block_cipher = None

# ── accumulate datas / binaries / hidden-imports ──────────────────
all_datas = [("config.json.example", ".")]
all_binaries: list = []
all_hidden: list = []


def _collect_tree(src_rel: str, dst_rel: str) -> list:
    """把源码目录下的文件收集为 datas。

    gui/styles 下的 QSS 与 SVG 图标由 :mod:`gui.styles.apply` /
    :mod:`gui.styles.icons` 在运行时以 ``Path(__file__).parent`` 读取，
    PyInstaller 不会自动包含这类非 .py 资源，必须显式打包。

    datas 二元组 ``(src, dest)`` 中的 ``dest`` 是**目录**：PyInstaller 会把文件
    放进该目录并保留其基名，��此这里传入文件所在的目标目录（而非文件全名）。
    """
    import glob

    root = os.path.join(_spec_dir, src_rel)
    if not os.path.isdir(root):
        print(f"[spec] skip missing data dir: {src_rel}")
        return []

    collected: list = []
    for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        # 跳过字节码缓存：PyInstaller 已单独处理 .pyc，无需再塞一份
        if "__pycache__" in path.split(os.sep):
            continue
        rel = os.path.relpath(path, root)
        dest_dir = os.path.join(dst_rel, os.path.dirname(rel))
        collected.append((path, dest_dir))
    return collected


# 主题样式与图标（缺失会导致打包后完全无样式）
all_datas += _collect_tree("gui/styles", "gui/styles")

# 应用图标
_icon_path = os.path.join(_spec_dir, "assets", "kvault.ico")
APP_ICON = _icon_path if os.path.isfile(_icon_path) else None
if APP_ICON is None:
    print("[spec] assets/kvault.ico not found, building without icon")

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

# llama-cpp-python 是可选依赖：装了就把原生库一起打包，没装则静默跳过。
# 该包自带编译好的 llama.cpp 二进制（llama_cpp/lib/*），必须整包收集，
# 否则打包后的程序无法加载 GGUF 模型。
_OPTIONAL_PKGS = [
    "llama_cpp",
]

for _pkg in _OPTIONAL_PKGS:
    try:
        _d, _b, _h = collect_all(_pkg)
        all_datas += _d
        all_binaries += _b
        all_hidden += _h
        print(f"[spec] bundled optional package: {_pkg}")
    except Exception:
        print(f"[spec] optional package not installed, skipped: {_pkg}")

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
    icon=APP_ICON,
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
