# Copilot instructions for KVault

## Project shape

KVault is a local-first Windows desktop knowledge-base application:

- `main.py` starts the PySide6 desktop application. `gui/` contains the Qt
  windows, panels, editors, styles, widgets, and `QThread` workers used for
  indexing and search. Keep slow I/O, parsing, embedding, and retrieval work
  out of the GUI thread.
- `core/` is the application backend. It owns configuration, document
  parsing/chunking/ingestion, embedding backends, ChromaDB vector storage,
  SQLite metadata, BM25/vector/hybrid retrieval, incremental updates,
  workspaces, and the Markdown note store.
- `mcp_server/` exposes the same backend through MCP. `mcp_server.tools`
  provides knowledge-base retrieval; `mcp_server.note_tools` provides vault
  operations. Keep MCP handlers thin and return the existing structured error
  dictionaries rather than leaking backend exceptions.
- `tests/` contains the pytest suite, including Qt widget tests and backend
  regression tests. `tests/conftest.py` supplies temporary configs and a
  deterministic fake embedder so most tests do not need Ollama.
- `KVault.spec` is the PyInstaller onedir build definition. The packaged
  application stores user data under `%APPDATA%\KVault`; source runs use the
  repository data directory.

The RAG path is: source file -> parser -> text splitter -> embedding backend
-> ChromaDB chunks, with document/chunk metadata in SQLite. Search can combine
vector retrieval with BM25 using RRF or weighted normalization. Incremental
updates compare stored file fingerprints and only reindex added or changed
files.

There are two related data surfaces. Imported external documents live under a
workspace's `files/` directory and are represented in the `documents` metadata
and vector indexes. User notes live as Markdown files under that workspace's
`vault/` directory. `core/vault.py` treats those Markdown files as the source
of truth; `core/note_store.py` maintains rebuildable SQLite note/link/tag
indexes and bridges notes into the existing document/vector retrieval path.

Each workspace has independent `files`, `vault`, `chroma_db`, and `kb.sqlite`
state below `data/workspaces/<workspace-id>/`. Use `WorkspaceManager` and its
resolved `Workspace` paths rather than constructing workspace paths ad hoc.

## Setup and commands

From PowerShell at the repository root:

```powershell
python -m venv .env
.\.env\Scripts\Activate.ps1
pip install -r requirements.txt
```

The normal desktop run is:

```powershell
python main.py
```

The test and lint commands are:

```powershell
pytest
pytest tests/test_config.py
pytest tests/test_config.py::test_config_load_creates_dirs
ruff check .
```

Replace `test_config_load_creates_dirs` with the desired test function; use
`pytest tests/gui/test_mainwindow_smoke.py::test_name` for a single GUI test.
The exact test names are discoverable with `pytest --collect-only -q`.

The MCP server runs over stdio by default, or SSE on a selected port:

```powershell
python -m mcp_server
python -m mcp_server --transport sse --port 8080
```

MCP note writes are deliberately disabled unless the process has
`KVAULT_ALLOW_WRITE=1`. `CHROMA_PATH` and `DB_PATH` can override the MCP
service's ChromaDB and SQLite locations.

Build the Windows packaged application with:

```powershell
.\.env\Scripts\Activate.ps1
pyinstaller KVault.spec
```

The result is `dist\KVault\KVault.exe`. Ollama must be running with the
configured embedding model for real embedding/indexing flows. Optional
capabilities are provided by `pdfplumber`, `rapidocr-onnxruntime`, `jieba`,
and `llama-cpp-python`; the code intentionally degrades when these are
absent.

## Repository-specific conventions

- Load and save settings through `core.config.Config`. Relative paths are
  resolved from the application base directory, and packaged builds use
  `%APPDATA%\KVault`; do not use the current working directory as an implicit
  data location.
- Pass workspace-specific paths/services through `WorkspaceManager`. When
  adding a workspace-aware operation, support the current workspace default
  and an explicit workspace id consistently with the existing GUI and MCP
  APIs.
- Treat Markdown files as authoritative. Update note content through
  `Vault`/`NoteStore`, then synchronize or rebuild indexes; never make SQLite
  note rows the only copy of user content.
- Route vault paths through `core.vault` normalization and boundary checks.
  Preserve relative paths with `/` separators at the vault API boundary, reject
  absolute/UNC/drive-letter and escaping paths, and retain the symlink
  containment check.
- Preserve existing note semantics: frontmatter supplies metadata such as
  title/aliases/tags, wiki links and tags are parsed by the core helpers, and
  duplicate note titles are resolved with the existing path/alias/title rules.
- Use `MetadataManager` for document/chunk/partition/tag persistence and
  `VectorStore` for ChromaDB access. Keep ingestion transactional in spirit:
  record failures with the document status/error path rather than silently
  returning a successful index.
- Select embedding implementations through the configured backend/factory
  (`ollama` or `llama_cpp`) instead of instantiating a backend directly in UI
  code. Tests should prefer the deterministic fake embedder fixture.
- Keep expensive GUI operations in workers and communicate with Qt signals.
  Follow the existing `IngestWorker`/`SearchWorker` pattern and ensure worker
  errors reach the UI or test signal rather than being swallowed.
- Preserve the MCP safety boundary: read-only tools work by default; note
  creation, append, and link updates must continue to require
  `KVAULT_ALLOW_WRITE=1`, enforce content/quantity limits, and return
  structured errors.
- Use the repository's standard `logging` modules for operational failures.
  Avoid broad silent fallbacks; optional dependency fallbacks should retain
  the documented degraded behavior and log it.
- Keep compatibility with the supported MCP SDK range. `mcp_server.server`
  already handles the `FastMCP`/`MCPServer` naming and SSE port differences;
  extend that compatibility layer rather than assuming one SDK version.
