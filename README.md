# Rapscallion Tools Suite for Sublime Text 4

A modular, high-performance productivity suite designed for Sublime Text 4 power users, support engineers, and developers. Built around atomic packages, non-blocking asynchronous workers, zero external dependencies, and unified `Rapscallion Tools` branding.

---

## Suite Packages

| Package | Purpose | Primary Shortcuts |
|---|---|---|
| **[RapscallionTools](RapscallionTools/)** | Core environment utilities: status bar path/git branch display, external media opener, folder session manager, and next/previous file cycling. | `Alt + Shift + E`<br>`Alt + [` / `Alt + ]` |
| **[RapscallionBookmarks](RapscallionBookmarks/)** | Visual bookmark manager featuring a floating Quick Panel with live scrolling preview and a dedicated bottom dock output panel. | `Alt + B`<br>`Alt + Shift + B`<br>`Ctrl + F2` |
| **[RapscallionNotes](RapscallionNotes/)** | Instant project scratchpad and Markdown notes editor with custom template engine. | `Alt + N`<br>`Alt + Shift + N` |
| **[RapscallionSILTools](RapscallionSILTools/)** | In-memory SQLite query engine and synchronized 10-column rainbow syntax highlighter for SIL database dumps and CSV logs. | `Alt + Q` |
| **[RapscallionZip](RapscallionZip/)** | Safe, read-only ZIP, JAR, WAR, and NUPKG archive inspector with virtual file navigation. | Mouse / Command |
| **[RapscallionSyntax](RapscallionSyntax/)** | Specialized syntax definitions and color schemes, including custom SL4 log highlighting. | Auto-assigned |

---

## Key Features Across the Suite

* **Zero External Dependencies:** Built strictly using Sublime Text 4's native Python 3.8 standard library and direct direct ST4 APIs (`sublime`, `sublime_plugin`).
* **Non-Blocking Concurrency:** Ingestion, file parsing, and archive extraction run on background worker threads (`threading.Thread`) with animated status bar spinners to guarantee smooth UI responsiveness.
* **Unified Preferences Integration:** All 6 packages register cleanly under **Preferences > Package Settings > Rapscallion Tools** with standardized command palettes and JSON schemas.
* **Live Sync via Directory Junctions:** Managed as a single monorepo in this repository, linked directly into Sublime Text's `Packages` directory via Windows directory junctions for seamless version control and instant testing.

---

## Project Structure

```text
rapscallion-sublime-tools/
├── .agents/
│   └── rules.md                  # Target runtime constraints and ST4 API conventions
├── RapscallionBookmarks/          # Bookmarks engine (Quick Panel, Output Panel, Gutters)
├── RapscallionNotes/              # Project notes manager & template editor
├── RapscallionSILTools/           # SIL SQLite query engine & rainbow syntax
├── RapscallionSyntax/             # SL4 log syntax and color schemes
├── RapscallionTools/              # Core status bar, media, session, navigation tools
├── RapscallionZip/                # Archive viewer and virtual tree extractor
├── .gitignore                     # Git ignore rules for caches and pycache
└── README.md                      # Suite documentation
```

---

## Installation & Development Setup

To link these packages directly into your live Sublime Text installation on Windows:

```powershell
# In PowerShell (Run as Administrator or Developer Mode enabled):
$packages = "C:\Users\$env:USERNAME\AppData\Roaming\Sublime Text\Packages"
$repo = "D:\_\Antigravity\Sublime"

@("RapscallionBookmarks", "RapscallionNotes", "RapscallionSILTools", "RapscallionSyntax", "RapscallionTools", "RapscallionZip") | ForEach-Object {
    cmd /c mklink /J "$packages\$_" "$repo\$_"
}
```

---

## License

Private repository. All rights reserved.
