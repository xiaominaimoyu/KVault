# KVault Copilot Instructions

## Project shape

KVault is a local-first Python 3.11+ PySide6 desktop knowledge base. `main.py` loads configuration, initializes logging and startup checks, then creates `gui.main_window.MainWindow`.

The application is split into four collaborating layers:

- `gui/` contains the Qt presentation layer, dialogs, panels, widgets, and `QThread` workers. Long-running ingest, search, and reindex operations are connected to the UI through Qt signals.
- `core/` is GUI-independent backend logic. The ingest path is parse -> split -> embed -> store vectors -> write metadata. Retrieval uses Chroma vector search and can optionally fuse it with BM25 through `core.hybrid_retriever`.
- Storage is local: original files, ChromaDB vectors, and SQLite metadata. `WorkspaceManager` gives each workspace its own `files`, `chroma_db`, and `kb.sqlite` directories.
- `mcp_server/` exposes read-only search, knowledge-base listing, and document-preview tools over MCP (`stdio` by default, optional SSE).

Embedding is fronted by `EmbeddingService` and selected through `BackendFactory`: Ollama is the default backend and llama.cpp is optional. Parsers and retrieval also have optional-dependency fallbacks; preserve those graceful degradation paths.

## Commands

Run commands from the repository root, preferably in the project virtual environment:

```powershell
python -m venv .env
.\.env\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the desktop application:

```powershell
python main.py
```

Run the full test suite:

```powershell
python -m pytest
```

Run one test file, one test function, or a focused test class:

```powershell
python -m pytest tests/test_config.py
python -m pytest tests/test_config.py::test_config_load_creates_dirs
python -m pytest tests/gui/test_mainwindow_smoke.py -q
```

The test configuration is in `pytest.ini`: tests are discovered under `tests/`, the repository root is on `PYTHONPATH`, and deprecation warnings are filtered. Tests should use the fixtures in `tests/conftest.py`; they provide temporary paths and a deterministic `FakeEmbedder` so tests do not require Ollama.

Lint and formatting checks:

```powershell
ruff check .
ruff format --check .
```

Build the Windows onedir package:

```powershell
pyinstaller KVault.spec
```

Run the MCP server:

```powershell
python -m mcp_server
python -m mcp_server --transport sse --port 8080
```

## Repository conventions

- Treat `config.json` as user/runtime state. Configuration paths are resolved relative to the application base directory, not the current working directory; packaged builds use `%APPDATA%\KVault` for data. Do not introduce cwd-dependent data paths.
- Keep the backend usable without Qt. Put parsing, indexing, retrieval, metadata, workspace, and migration behavior in `core/`; GUI code should coordinate those services rather than duplicate them.
- Keep SQLite metadata and Chroma vector state synchronized. Document IDs are UUIDs; chunk IDs follow `<document_id>_<chunk_index>`. Ingest records failed status and the error message before re-raising, and deletion/reindex paths must clean up both metadata and vectors.
- Use `WorkspaceManager` when resolving active storage. Do not read or write the legacy/global data directories directly when a workspace-specific path is available.
- Preserve the embedding backend abstraction. New backends belong under `core/embedding_backends/`, are selected by `BackendFactory`, and must retain the existing availability/model-availability checks and dimension consistency behavior.
- Preserve optional dependency behavior. Missing `pdfplumber`, `rapidocr-onnxruntime`, or `jieba` should degrade only the related feature, with the established logging/fallback behavior.
- Keep blocking work off the Qt event loop. Extend the existing worker/signal pattern instead of calling ingest, embedding, or retrieval synchronously from UI slots.
- Escape user-controlled text before rendering it as HTML in Qt widgets. Existing UI code uses `html.escape`; retain that boundary for document names, previews, tags, and search content.
- MCP tools are intentionally read-only. Keep public tool functions bounded and error-shaped like the existing API, honor `CHROMA_PATH` and `DB_PATH`, and reset the service cache when tests or configuration changes require it.
- Metadata schema changes go through `core/schema_migrator.py`; do not silently alter the live SQLite schema in an unrelated manager method.
- When changing behavior, add focused tests alongside the relevant area. Prefer temporary SQLite/Chroma paths and `FakeEmbedder` fixtures over real model services or user data.

## Useful source references

- `README.md`: installation, runtime prerequisites, supported formats, MCP usage, packaging, and migration cautions.
- `docs/00-kvault架构总览.md`: intended layer boundaries and storage/RAG flow.
- `.codeartsdoer/AGENTS.md`: repository context identifies Python as the project language.
