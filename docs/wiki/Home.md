# Rapscallion Tools Suite for Sublime Text 4

A modular, high-performance productivity suite for Sublime Text 4 power users, support engineers, and developers.

## Design Philosophy
- **Zero External Dependencies**: Runs purely on Sublime Text 4's native **Python 3.8** standard library (`sqlite3`, `zipfile`, `http.server`, `csv`, `json`, `html`) and `sublime` / `sublime_plugin` APIs.
- **Non-Blocking Concurrency**: Heavy parsing, SQLite ingestion, and file scanning execute on background worker threads with UI updates marshalled safely via `sublime.set_timeout`.
- **Unified UX**: Standardized `Raps: <Tool> - <Action>` Command Palette captions, `Ctrl+Alt+<Key>` chord prefixes, and **Preferences > Package Settings > Rapscallion Tools** integration.
- **Package Isolation**: All 8 packages operate independently without cross-package Python imports.

## Suite Packages

| Package | Purpose | Primary Chord | Guide |
| :--- | :--- | :--- | :--- |
| **RapscallionTools** | Hex decoder, status bar metrics/git branch, external media opener, folder sessions, timestamps, XML jump | `Ctrl+Alt+U` / `Ctrl+Alt+H` | [RapscallionTools](RapscallionTools) |
| **RapscallionBookmarks** | Visual HTML side panel, Quick Panel live preview, bottom dock panel, gutters, Markdown export | `Ctrl+Alt+B` | [RapscallionBookmarks](RapscallionBookmarks) |
| **RapscallionMarkdown** | Live `minihtml` side panel, localhost SSE browser preview, clickable task checkboxes, cursor-line highlight | `Ctrl+Alt+M` | [RapscallionMarkdown](RapscallionMarkdown) |
| **RapscallionNotes** | Project scratchpad & Markdown notes with path rules and customizable templates | `Ctrl+Alt+N` | [RapscallionNotes](RapscallionNotes) |
| **RapscallionSILTools** | In-memory SQLite query engine, 10-column rainbow syntax, field hover inspector, table aligner | `Ctrl+Alt+I` | [RapscallionSILTools](RapscallionSILTools) |
| **RapscallionEWicParser** | Buypass/FIS, RBSLynk ISO, & WinEPS POS log decoder, TLV unpacker, APL cross-referencing | `Ctrl+Alt+W` | [RapscallionEWicParser](RapscallionEWicParser) |
| **RapscallionZip** | Safe, read-only `ZIP`, `JAR`, `WAR`, and `NUPKG` archive tree explorer & extractor | `Ctrl+Alt+Z` | [RapscallionZip](RapscallionZip) |
| **RapscallionSyntax** | Domain-specific `.sublime-syntax` definitions (`SL4`, `LOC`, etc.) and color schemes | *Auto-assigned* | [RapscallionSyntax](RapscallionSyntax) |

## Quick Links
- [Installation & Setup](Installation-and-Setup) — Install via `install.ps1` live junctions, copy mode, or `.sublime-package` releases.
- [Key Chords & Command Palette](Key-Chords-and-Command-Palette) — Complete shortcut cheat sheet.
- [Architecture & Contributing](Architecture-and-Contributing) — Python 3.8 rules, `HtmlSheet` patterns, and CI/release pipeline.
