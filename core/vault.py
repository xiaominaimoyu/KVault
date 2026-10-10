"""Vault 目录模型：笔记以普通 Markdown 文件存放于磁盘上的文件夹中。

这是 KVault 向 Obsidian 靠拢的核心设计——**知识库就是你自己的文件夹**：

- 每份笔记都是一个真实的 ``.md`` 文件，可被任意编辑器、Git、同步盘处理
- SQLite 中的记录只是索引，删除索引不会丢失任何数据
- 目录层级被保留，不再出现「同名文件互相覆盖」的问题

安全约束（防止笔记内容或外部输入把文件写到 vault 之外）：

- 拒绝绝对路径、盘符、UNC 路径与 ``..`` 上跳
- 解析软链接后再次校验目标仍在 vault 根目录内
"""

from __future__ import annotations

import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MARKDOWN_SUFFIX = ".md"

#: 遍历时跳过的目录名（Obsidian 配置、版本库、构建产物等）
IGNORED_DIRS = frozenset(
    {
        ".obsidian",
        ".trash",
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".idea",
        ".vscode",
    }
)

#: 笔记标题中必须剔除的字符——它们会破坏 wiki 链接语法或文件系统路径
_ILLEGAL_TITLE_CHARS = re.compile(r'[\[\]#^|<>:"*?\\/]')

# Windows 保留设备名
_RESERVED_NAMES = frozenset(
    [
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    ]
)

_MAX_TITLE_LEN = 100


class VaultError(Exception):
    """Vault 操作失败的基类。"""


class UnsafePathError(VaultError):
    """请求的路径越界或格式非法，已被拒绝。"""


class NoteNotFoundError(VaultError):
    """目标笔记不存在。"""


class NoteExistsError(VaultError):
    """目标笔记已存在，且调用方要求不覆盖。"""


@dataclass(frozen=True)
class VaultNote:
    """磁盘上一份笔记的轻量描述。"""

    path: str
    """相对 vault 根目录的路径，统一使用 ``/`` 分隔，例如 ``项目/计划.md``。"""

    title: str
    """显示标题，优先取 frontmatter 的 ``title`` 或正文 H1，最后回退为文件名。"""

    size: int = 0
    mtime: float = 0.0

    @property
    def name(self) -> str:
        """不含扩展名的文件名。"""
        return self.path.rsplit("/", 1)[-1][: -len(MARKDOWN_SUFFIX)]

    @property
    def folder(self) -> str:
        """所在子目录，根目录下的笔记返回空字符串。"""
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""

    @property
    def modified(self) -> datetime | None:
        return datetime.fromtimestamp(self.mtime) if self.mtime else None


# --------------------------------------------------------------------------
# 路径处理
# --------------------------------------------------------------------------


def sanitize_title(title: str) -> str:
    """把任意标题整理成可安全用作文件名的形式。"""
    name = unicodedata.normalize("NFC", title or "").strip()
    name = _ILLEGAL_TITLE_CHARS.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    # 控制字符
    name = "".join(ch for ch in name if ch.isprintable())
    if not name:
        return "未命名笔记"
    if len(name) > _MAX_TITLE_LEN:
        name = name[:_MAX_TITLE_LEN].rstrip()
    if name.split(".")[0].upper() in _RESERVED_NAMES:
        name = f"_{name}"
    return name


def normalize_rel_path(rel_path: str) -> str:
    """把外部输入规整为安全的相对路径。

    统一使用 ``/`` 分隔，去除 ``.``、解析 ``..``、丢弃空段与首尾斜杠。

    :raises UnsafePathError: 路径为绝对路径、含盘符，或上跳出了根目录
    """
    if rel_path is None:
        raise UnsafePathError("路径不能为 None")

    raw = str(rel_path).replace("\\", "/").strip()
    if not raw:
        return ""

    # 盘符前缀（C:、C:/foo）与 UNC 前缀（//server/share）
    if re.match(r"^[A-Za-z]:", raw):
        raise UnsafePathError(f"不允许使用绝对路径: {rel_path}")
    if raw.startswith("//"):
        raise UnsafePathError(f"不允许使用网络路径: {rel_path}")
    # 以 / 开头为绝对路径。静默转成 vault 内相对路径会创建出用户没预期的目录，
    # 与其悄悄改写语义，不如明确拒绝。
    if raw.startswith("/"):
        raise UnsafePathError(f"不允许使用绝对路径: {rel_path}")

    parts: list[str] = []
    for segment in raw.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not parts:
                raise UnsafePathError(f"路径越界: {rel_path}")
            parts.pop()
            continue
        parts.append(segment)

    if not parts:
        return ""
    return "/".join(parts)


@dataclass
class NoteIndex:
    """全部笔记的检索索引，用于 wiki 链接解析与快速跳转。"""

    notes: dict[str, VaultNote] = field(default_factory=dict)
    """``相对路径`` -> 笔记。"""

    _by_name: dict[str, list[str]] = field(default_factory=dict)
    """小写文件名 -> 相对路径列表（同名文件可能有多个）。"""

    _by_alias: dict[str, list[str]] = field(default_factory=dict)
    """小写别名 -> 相对路径列表。"""

    _by_title: dict[str, list[str]] = field(default_factory=dict)
    """小写标题 -> 相对路径列表。"""

    def add(self, note: VaultNote, aliases: list[str] | None = None) -> None:
        self.notes[note.path] = note
        self._by_name.setdefault(note.name.lower(), []).append(note.path)
        if note.title:
            self._by_title.setdefault(note.title.lower(), []).append(note.path)
        for alias in aliases or []:
            cleaned = alias.strip()
            if cleaned:
                self._by_alias.setdefault(cleaned.lower(), []).append(note.path)

    def __len__(self) -> int:
        return len(self.notes)

    def __contains__(self, rel_path: object) -> bool:
        return rel_path in self.notes

    def get(self, rel_path: str) -> VaultNote | None:
        return self.notes.get(rel_path)

    @property
    def paths(self) -> list[str]:
        return sorted(self.notes)

    def resolve(self, target: str, from_path: str = "") -> str | None:
        """按 Obsidian 规则解析 wiki 链接目标，返回相对路径。

        依次尝试：显式路径、同目录相对路径、全库同名、同库别名、标题、忽略大小写兜底。
        多个候选时取路径最短者，贴近 Obsidian 的消歧行为。
        """
        from core.links import normalize_target

        name = normalize_target(target)
        if not name:
            return None

        # 1) 显式相对路径
        for candidate in (f"{name}{MARKDOWN_SUFFIX}", name):
            if candidate in self.notes:
                return candidate

        # 2) 相对来源笔记所在目录
        if from_path and "/" in from_path:
            base = from_path.rsplit("/", 1)[0]
            relative = f"{base}/{name}{MARKDOWN_SUFFIX}"
            if relative in self.notes:
                return relative

        # 3~5) 按文件名 / 别名 / 标题查找
        for lookup in (self._by_name, self._by_alias, self._by_title):
            hits = lookup.get(name.lower())
            if hits:
                return min(hits, key=lambda p: (p.count("/"), len(p)))

        return None


class Vault:
    """一组 Markdown 文件构成的笔记库。"""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()
        self._index = NoteIndex()

    # ---------------------------------------------------------------- 路径

    def abspath(self, rel_path: str) -> Path:
        """把相对路径解析为绝对路径，并确保它没有逃出 vault 根目录。

        :raises UnsafePathError: 越界或指向根目录之外（含软链接外指）
        """
        normalized = normalize_rel_path(rel_path)
        candidate = self.root / normalized if normalized else self.root
        resolved = Path(os.path.normpath(candidate))

        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise UnsafePathError(f"路径越界: {rel_path}") from exc

        # 软链接可能指向根目录之外，必须校验真实路径
        if resolved.exists():
            real = resolved.resolve()
            try:
                real.relative_to(self.root)
            except ValueError as exc:
                raise UnsafePathError(f"路径经软链接越界: {rel_path}") from exc
            return real

        # 目标尚不存在：校验其最近的已存在父目录
        parent = resolved.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        real_parent = parent.resolve()
        try:
            real_parent.relative_to(self.root)
        except ValueError as exc:
            raise UnsafePathError(f"路径经软链接越界: {rel_path}") from exc
        return resolved

    def to_rel(self, path: str | Path) -> str:
        """把绝对路径转换为相对路径表示。"""
        candidate = Path(path)
        if not candidate.is_absolute():
            return normalize_rel_path(str(path))
        return normalize_rel_path(str(candidate.resolve().relative_to(self.root)))

    def exists(self, rel_path: str) -> bool:
        try:
            return self.abspath(rel_path).is_file()
        except UnsafePathError:
            return False

    # ------------------------------------------------------------ 唯一命名

    def unique_path(self, folder: str, title: str) -> str:
        """生成不冲突的笔记路径，冲突时追加数字后缀。

        ``("项目", "计划")`` 依次可能得到 ``项目/计划.md``、``项目/计划 1.md``。
        """
        name = sanitize_title(title)
        folder = normalize_rel_path(folder) if folder else ""
        prefix = f"{folder}/" if folder else ""

        candidate = f"{prefix}{name}{MARKDOWN_SUFFIX}"
        if not self.exists(candidate):
            return candidate

        for i in range(1, 10_000):
            candidate = f"{prefix}{name} {i}{MARKDOWN_SUFFIX}"
            if not self.exists(candidate):
                return candidate

        raise NoteExistsError(f"无法为「{title}」生成唯一文件名")

    # ---------------------------------------------------------------- 读取

    def read(self, rel_path: str) -> str:
        """读取笔记全文。"""
        target = self.abspath(rel_path)
        if not target.is_file():
            raise NoteNotFoundError(f"笔记不存在: {rel_path}")
        return target.read_text(encoding="utf-8")

    def stat(self, rel_path: str) -> VaultNote | None:
        """获取笔记的元信息，不读取正文。"""
        try:
            target = self.abspath(rel_path)
        except UnsafePathError:
            return None
        if not target.is_file():
            return None
        info = target.stat()
        return VaultNote(
            path=normalize_rel_path(rel_path),
            title=sanitize_title(Path(rel_path).stem),
            size=info.st_size,
            mtime=info.st_mtime,
        )

    def iter_paths(self) -> list[str]:
        """遍历 vault 内全部 Markdown 文件的相对路径（已跳过隐藏与忽略目录）。"""
        results: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(
                d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")
            )
            for name in sorted(filenames):
                if not name.lower().endswith(MARKDOWN_SUFFIX) or name.startswith("."):
                    continue
                full = Path(dirpath) / name
                results.append(normalize_rel_path(str(full.relative_to(self.root))))
        return results

    def list_notes(self) -> list[VaultNote]:
        """列出全部笔记。"""
        notes: list[VaultNote] = []
        for rel in self.iter_paths():
            note = self.stat(rel)
            if note is not None:
                notes.append(note)
        return notes

    # ---------------------------------------------------------------- 写入

    def create(self, title: str, folder: str = "", content: str = "", overwrite: bool = False) -> str:
        """新建笔记，返回相对路径。

        默认使用 :meth:`unique_path` 自动去重；``overwrite=True`` 时强制使用
        原始路径，已存在则抛出 :class:`NoteExistsError`。
        """
        if overwrite:
            rel = f"{normalize_rel_path(folder)}/{sanitize_title(title)}{MARKDOWN_SUFFIX}" if folder else f"{sanitize_title(title)}{MARKDOWN_SUFFIX}"
            rel = normalize_rel_path(rel)
            if self.exists(rel):
                raise NoteExistsError(f"笔记已存在: {rel}")
        else:
            rel = self.unique_path(folder, title)

        target = self.abspath(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
        return rel

    def write(self, rel_path: str, content: str) -> None:
        """覆盖写入笔记正文，自动创建缺失的父目录。"""
        target = self.abspath(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def delete(self, rel_path: str) -> None:
        """删除笔记文件。文件不存在时静默返回。"""
        target = self.abspath(rel_path)
        if target.is_file():
            target.unlink()
        self._prune_empty_dirs(target.parent)

    def rename(self, rel_path: str, new_title: str, new_folder: str | None = None) -> str:
        """重命名（并可移动目录），返回新的相对路径。

        目标已存在时自动追加数字后缀，绝不覆盖既有笔记。
        """
        source = self.abspath(rel_path)
        if not source.is_file():
            raise NoteNotFoundError(f"笔记不存在: {rel_path}")

        old_folder = normalize_rel_path(rel_path).rsplit("/", 1)[0] if "/" in rel_path else ""
        folder = normalize_rel_path(new_folder) if new_folder is not None else old_folder
        dest_rel = self.unique_path(folder, new_title)
        dest = self.abspath(dest_rel)

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))
        self._prune_empty_dirs(source.parent)
        return dest_rel

    def move(self, rel_path: str, folder: str) -> str:
        """把笔记移动到指定目录，保持文件名不变。"""
        name = normalize_rel_path(rel_path).rsplit("/", 1)[-1]
        stem = name[: -len(MARKDOWN_SUFFIX)]
        return self.rename(rel_path, stem, new_folder=folder)

    # ------------------------------------------------------------ 索引与查找

    @property
    def index(self) -> NoteIndex:
        """最近一次 :meth:`reindex` 建立的索引。"""
        return self._index

    def reindex(self, alias_map: dict[str, list[str]] | None = None) -> NoteIndex:
        """重建笔记索引。

        :param alias_map: 相对路径 -> 别名列表，用于别名解析
        """
        from core.frontmatter import parse
        from core.title import title_from_content

        index = NoteIndex()
        for rel in self.iter_paths():
            note = self.stat(rel)
            if note is None:
                continue
            try:
                text = self.read(rel)
            except (OSError, UnicodeDecodeError):
                continue
            fm = parse(text)
            title = fm.title or title_from_content(text) or note.name
            enriched = VaultNote(
                path=note.path, title=title, size=note.size, mtime=note.mtime
            )
            index.add(enriched, aliases=(alias_map or {}).get(rel, fm.aliases))
        self._index = index
        return index

    def resolve_link(self, target: str, from_path: str = "") -> str | None:
        """解析 wiki 链接目标，使用当前索引。"""
        return self._index.resolve(target, from_path)

    def unique_candidates(self, fragment: str, limit: int = 20) -> list[str]:
        """模糊匹配笔记路径，供快速切换与补全使用。"""
        fragment = (fragment or "").strip().lower()
        if not fragment:
            return []

        scored: list[tuple[int, str]] = []
        for rel, note in self._index.notes.items():
            haystacks = (note.name.lower(), note.path.lower(), note.title.lower())
            if any(fragment in h for h in haystacks):
                # 命中文件名最靠前的排前面
                score = haystacks.index(next(h for h in haystacks if fragment in h))
                scored.append((score, rel))

        scored.sort(key=lambda item: (item[0], item[1]))
        return [rel for _score, rel in scored[:limit]]

    def title_from_path(self, rel_path: str) -> str:
        """由路径推导显示标题（不含扩展名）。"""
        return Path(normalize_rel_path(rel_path)).stem

    # ---------------------------------------------------------------- 内部

    def _prune_empty_dirs(self, directory: Path) -> None:
        """向上清理空目录，直到触及 vault 根目录。"""
        current = directory
        while current != self.root and self.root in current.parents:
            try:
                if current.is_dir() and not any(current.iterdir()):
                    current.rmdir()
                else:
                    return
            except OSError:
                return
            current = current.parent

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"Vault(root={self.root}, notes={len(self._index)})"