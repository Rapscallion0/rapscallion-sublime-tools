# Sublime Text Package Architecture & Development Rules

This document defines the strict development standards, architectural patterns, runtime constraints, and coding conventions across the Sublime Text packages in this workspace:
- **`RapscallionTools`** (`c:/Users/KevinSommers/AppData/Roaming/Sublime Text/Packages/RapscallionTools`) — Core utilities, status bar, media preview, sessions, navigation.
- **`RapscallionBookmarks`** (`c:/Users/KevinSommers/AppData/Roaming/Sublime Text/Packages/RapscallionBookmarks`) — Visual HTML side-panel bookmark manager.
- **`RapscallionNotes`** (`c:/Users/KevinSommers/AppData/Roaming/Sublime Text/Packages/RapscallionNotes`) — Automated ticket notes & template editor.
- **`RapscallionZip`** (`c:/Users/KevinSommers/AppData/Roaming/Sublime Text/Packages/RapscallionZip`) — Interactive archive tree explorer and extractor.
- **`RapscallionSILTools`** (`c:/Users/KevinSommers/AppData/Roaming/Sublime Text/Packages/RapscallionSILTools`) — SIL data dump parser, field hover, and SQLite query engine.
- **`RapscallionSyntax`** (`c:/Users/KevinSommers/AppData/Roaming/Sublime Text/Packages/RapscallionSyntax`) — Domain syntax definitions.

All agents working on these packages must adhere to these guidelines without deviation.

---

## 1. Target Runtime Constraints

### 1.1 Python 3.8 Environment
- **Sublime Text 4 Engine**: The plugin host runs Python **3.8** (as enforced by `.python-version`).
- **No Python 3.9+ Features**:
  - ❌ Do NOT use `str.removeprefix()` or `str.removesuffix()`. Use standard slicing or regex.
  - ❌ Do NOT use dictionary union operators (`dict1 | dict2`). Use `{**dict1, **dict2}` or `.update()`.
  - ❌ Do NOT use built-in collection types in type annotations (e.g. `list[str]`). Use `typing.List[str]` if typing is used, or omit annotations in line with existing codebase style.
  - ❌ Do NOT use `match/case` statements (Python 3.10+). Use `if/elif/else`.

### 1.2 Zero External Dependencies
- **Standard Library Only**: All code must execute using Python 3.8's standard library and the native `sublime` / `sublime_plugin` modules.
- **Never rely on `pip` / PyPI**: Do not introduce third-party libraries (e.g. `requests`, `pandas`, `numpy`, `bs4`). 
- **Available Native Tooling**: Use standard modules:
  - `sqlite3` for fast in-memory querying and relational operations.
  - `zipfile` for archive introspection and stream reading.
  - `csv`, `json`, `io` for structured data serialization.
  - `subprocess`, `urllib.parse`, `shutil`, `getpass`, `platform` for OS interactions.
  - `html` for safe escaping before rendering minihtml.
  - `winreg` guarded by `sys.platform.startswith("win")` for Windows registry lookups.

### 1.3 Sublime Text 4 API Standards
- **Syntax Assignment**: Always use `view.assign_syntax(...)`. 
  - ❌ Do NOT use the deprecated `view.set_syntax_file(...)`.
- **Completion APIs**: Return `sublime.CompletionList` containing `sublime.CompletionItem` or `sublime.CompletionItem.snippet_completion` instances. Use completion flags such as `sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS`.
- **HTML Sheets**: Use `window.new_html_sheet(name, html_content, group=...)` for rich dashboard/sidebar interfaces rather than raw text buffers where appropriate.
- **Color Scheme Integration**: Utilize modern Sublime CSS variables in popups and HTML sheets:
  - `var(--background)`, `var(--foreground)`, `var(--yellowish)`, `var(--bluish)`, etc.
  - Use `color-mix(in srgb, ...)` for tinted backgrounds and opacity variations.
  - Query theme colors dynamically via `view.style_for_scope(scope)` with fallback palette arrays.

---

## 2. Detected Architectural Patterns

### 2.1 State Management & Persistence

| Scope | Storage Mechanism | Established Path / Key | Examples |
| :--- | :--- | :--- | :--- |
| **Workspace / Project State** | `.sublime/` JSON in folder root | `<project_root>/.sublime/*.json` | `.sublime/RapscallionBooks.json`<br>`.sublime/folder-session.json`<br>`.sublime/.notes.md` |
| **Package Preferences** | `<PackageName>.sublime-settings` | `Packages/<PackageName>/<PackageName>.sublime-settings` | `RapscallionTools.sublime-settings`<br>`SILTools.sublime-settings`<br>`RapscallionBookmarks.sublime-settings` |
| **View-Level State** | `view.settings()` | Prefixed boolean or mapping keys | `"is_rapscallion_zip_view"`<br>`"is_sil_sql_panel"`<br>`"is_rapscallion_template_buffer"` |
| **Window-Level State** | `window.settings()` | Prefixed state flags | `"rapscallion_bookmarks_sheet"` |

#### Project Path Resolution Rule
When persisting project data, always check for active project folders using `window.folders()`:
```python
def get_project_root(window):
    folders = window.folders()
    return folders[0] if folders else None
```
Ensure directory creation uses `os.makedirs(dir_path, exist_ok=True)`.

### 2.2 Scratch Buffers & Virtual Interfaces
For custom inspectors, trees, and editors (such as `rapscallion_zip`, `sil_sqlite_query`, `template_editor`):
1. **Creation**: Create with `window.new_file()`, set an explicit title via `view.set_name(...)`, and mark as scratch `view.set_scratch(True)` to prevent save prompts on close.
2. **Buffer Tagging**: Tag the view with a distinct setting identifier:
   ```python
   view.settings().set("is_rapscallion_zip_view", True)
   ```
3. **Read-Only Lock / Unlock Cycle**: Always unlock before updating text, then re-lock:
   ```python
   view.set_read_only(False)
   view.replace(edit, sublime.Region(0, view.size()), rendered_content)
   view.set_read_only(True)
   view.set_scratch(True)
   ```
4. **Command Interception**: Intercept commands in scratch buffers using `EventListener.on_text_command`:
   ```python
   def on_text_command(self, view, command_name, args):
       if command_name == "save" and view.settings().get("is_rapscallion_template_buffer"):
           self.commit_template(view)
           return ("noop", None) # Cancel default disk save
       return None
   ```

### 2.3 Interactive Views & HTML Sheets
- **Side Panel Layouts**: Adjust window layouts using `window.set_layout(...)` with 2-column specifications:
  - Left panel: `{"cols": [0.0, width, 1.0], "rows": [0.0, 1.0], "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]}`
  - Right panel: `{"cols": [0.0, 1.0 - width, 1.0], "rows": [0.0, 1.0], "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]}`
- **Layout Guarding**: Use an `EventListener` (like `RapscallionPanelGuardListener`) to:
  - Prevent user editors from being placed in the panel group.
  - Automatically collapse layout (`window.set_layout({"cols": [0.0, 1.0], ...})`) when the sheet or all panel views close.
  - Persist resized panel ratios (`save_current_panel_width`).
- **Dynamic Width Calibration**: Calculate responsive character budgets using `view.viewport_extent()[0]` to format truncated lists cleanly.

### 2.4 Popups & Minihtml Tooltips
- Always escape text injected into HTML using `html.escape()`.
- Use `view.show_popup(html, max_width=..., flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY)`.
- Support hyperlink navigation with `href="action:<command>?param=..."` and parse handlers.

---

## 3. API & Concurrency Standards

### 3.1 Command Type Selection Hierarchy

| Command Type | Base Class | When to Use | Edit Token Access |
| :--- | :--- | :--- | :--- |
| **Buffer Commands** | `sublime_plugin.TextCommand` | Direct buffer reading/writing, selection changes, character insertions. | `run(self, edit, **kwargs)` |
| **Window Commands** | `sublime_plugin.WindowCommand` | Opening files, quick panels, input panels, layout manipulation, multi-view orchestration. | No `edit` token |
| **Global / App Commands** | `sublime_plugin.ApplicationCommand` | Global preference toggles, cross-window settings adjustments. | No `edit` token |

### 3.2 The Strict Edit Token Rule
> [!CRITICAL]
> Sublime Text invalidates `edit` tokens the moment `TextCommand.run()` completes.
> - **NEVER** store an `edit` token in an instance attribute (`self.edit = edit`).
> - **NEVER** pass an `edit` token to `sublime.set_timeout`, `sublime.set_timeout_async`, or background threads.
> - **External/Asynchronous Buffer Edits**: To insert or replace text into a view from outside synchronous `TextCommand.run()`, call `view.run_command("append", {"characters": ...})` or implement a dedicated helper `TextCommand`.

### 3.3 Asynchronous Execution & Threading
- **Offload Heavy I/O**: Operations taking >10ms (file scanning, SQLite parsing, zip unpacking, external process checks) MUST execute in a background thread:
  ```python
  threading.Thread(target=self._worker_task, args=(...), daemon=True).start()
  ```
- **Async Event Listeners**: Prefer `_async` listener methods for non-blocking telemetry, status bar recalculations, and background updates:
  - `on_activated_async(self, view)`
  - `on_post_save_async(self, view)`
  - `on_modified_async(self, view)`
  - `on_selection_modified_async(self, view)`
- **UI Thread Marshalling**: Always dispatch UI interactions (panels, popups, status messages, view creation) back to the main thread via:
  ```python
  sublime.set_timeout(lambda: self._ui_callback(), 0)
  ```
- **SQLite Concurrency**: When using in-memory SQLite across background threads and UI callbacks, use `check_same_thread=False`:
  ```python
  conn = sqlite3.connect(":memory:", check_same_thread=False)
  ```

### 3.4 Status Bar Protocols
- **Namespaced Keys**: Assign view status items using package-specific keys:
  - `sb_info` (RapscallionTools file metrics)
  - `sil_col_indicator` (SILTools column counter)
  - `sil_query_progress` (SILTools query progress spinner)
- **Immediate Cleanup**: Call `view.erase_status(key)` whenever a view deactivates, the feature is disabled, or data is invalid.
- **Selection Guarding**: Always check `view.sel()` length before indexing `sel[0]` to prevent `IndexError` on virtual or unselected buffers.
- **Progress Animation Pattern**: Use a cycling frame spinner via recursive `sublime.set_timeout` (e.g. `SilProgressIndicator` with `["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]`).

---

## 4. Naming & Settings Conventions

### 4.1 Class & Command Naming
- **Class Names**: Use PascalCase ending with the command type suffix:
  - `Rapscallion<Action>Command` (e.g., `RapscallionToggleSidePanelCommand`, `RapscallionRenderZipTreeCommand`)
  - `Sil<Action>Command` (e.g., `SilSqliteQueryCommand`, `SilShowDocsCommand`)
- **Internal Command Names**: Sublime automatically converts PascalCase to snake_case without the suffix:
  - `RapscallionToggleSidePanelCommand` ➔ `rapscallion_toggle_side_panel`
  - `SilSqliteQueryCommand` ➔ `sil_sqlite_query`
  - `JumpXmlTagCommand` ➔ `jump_xml_tag`

### 4.2 Command Palette Captions (`Default.sublime-commands`)
Format: `<PackageName>: <Descriptive Action>`
```json
[
    {
        "caption": "RapscallionTools: Toggle Status Bar Info",
        "command": "rapscallion_toggle_status_bar"
    },
    {
        "caption": "SILTools: Query with SQLite",
        "command": "sil_sqlite_query"
    },
    {
        "caption": "Preferences: RapscallionTools Settings",
        "command": "edit_settings",
        "args": {
            "base_file": "${packages}/RapscallionTools/RapscallionTools.sublime-settings",
            "default": "{\n\t$0\n}\n"
        }
    }
]
```

### 4.3 Keymap & Context Definitions (`Default (Windows).sublime-keymap`)
Always scope key bindings to prevent collision with core Sublime keys or other packages:
```json
[
    {
        "keys": ["enter"],
        "command": "rapscallion_activate_zip_item",
        "context": [
            { "key": "setting.is_rapscallion_zip_view", "operator": "equal", "operand": true }
        ]
    },
    {
        "keys": ["alt+m"],
        "command": "jump_xml_tag",
        "context": [
            { "key": "selector", "operator": "equal", "operand": "text.xml, embedding.xml" }
        ]
    }
]
```

### 4.4 Settings Structure (`<PackageName>.sublime-settings`)
- Organize settings files with clean visual separator blocks:
  ```json
  // =========================================================================
  // Section Header
  // =========================================================================
  ```
- Always supply sensible defaults in Python calls:
  ```python
  def get_setting(key, default=None):
      s = sublime.load_settings(SETTINGS_FILE)
      return s.get(key, default)
  ```
- Save modified settings programmatically with `sublime.save_settings(SETTINGS_FILE)`.

---

## 5. Syntax Definitions & Color Schemes

### 5.1 Sublime Syntax Standards (`.sublime-syntax`)
- Must declare `%YAML 1.2` at line 1.
- Use explicit header metadata: `name`, `file_extensions`, and root `scope`.
- Follow Sublime scoping conventions:
  - Keywords: `keyword.control.*`, `keyword.other.*`
  - Types / Functions: `support.type.*`, `support.function.*`, `entity.name.function.*`
  - Identifiers: `variable.parameter.*`, `variable.other.*`
  - Sequences / Brackets: `punctuation.separator.*`, `punctuation.section.*`
- For stateful rotations (e.g. rainbow columns in `SIL (Rainbow)`):
  - Push into dedicated column contexts on delimiters:
    ```yaml
    col1_header:
      - match: ','
        scope: punctuation.separator.sequence
        set: col2_header
      - include: header_end
      - match: '[A-Za-z0-9_]+'
        scope: markup.deleted.sil markup.rainbow1
    ```

---

## 6. Code Style, Logging & Agent Boundaries

### 6.1 Logging & User Feedback
- **Console Output**: Always prefix debug/warning messages with the package tag:
  ```python
  print(f"[RapscallionTools] Launch failed: {exc}")
  ```
- **Status Bar Feedback**: Keep status bar messages concise, optionally tagged:
  ```python
  sublime.status_message("RapscallionBookmarks: Save file before bookmarking.")
  sublime.status_message(f"SIL Query: {len(rows)} rows returned in {elapsed}ms.")
  ```
- **Error Dialogs**: Use `sublime.error_message(...)` ONLY for user-initiated actions that fail fatally:
  ```python
  sublime.error_message("SQL Syntax/Execution Error:\n" + str(e))
  ```

### 6.2 Error Handling & Resilience
- **Graceful Degradation**: Guard file parsing and external process calls against missing binaries, permission issues, or corrupt files.
- **Always Close Resources**: Wrap file and SQLite operations in `try/finally` or context managers:
  ```python
  def safe_close(self, conn):
      try:
          conn.close()
      except Exception:
          pass
  ```
- **Never Raise Unhandled Exceptions in Event Listeners**: Any uncaught exception inside an `EventListener` can disrupt Sublime Text's global event pipeline. Wrap listener logic in robust try/except blocks.

### 6.3 Package Isolation & Agent Boundaries
- **Strict Package Independence**:
  - `RapscallionTools`, `RapscallionBookmarks`, `RapscallionNotes`, `RapscallionZip`, `RapscallionSILTools`, and `RapscallionSyntax` are independent packages.
  - Do NOT create direct cross-package Python imports.
  - Inter-package coordination must occur via:
    - View settings (`view.settings().get("is_rapscallion_zip_view")`)
    - Global window settings (`window.settings()`)
    - Public commands (`view.run_command(...)` / `window.run_command(...)`)
- **Preserve Existing Comments**: Retain docstrings, config documentation, and inline comments when editing package files.
- **Atomic Modifications**: Edits must be focused and surgically targeted to preserve existing functionality.
