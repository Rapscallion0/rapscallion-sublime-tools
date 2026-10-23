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
├── .github/
│   └── workflows/package.yml     # Automated package builder & release CI
├── RapscallionBookmarks/          # Bookmarks engine (Quick Panel, Output Panel, Gutters)
├── RapscallionNotes/              # Project notes manager & template editor
├── RapscallionSILTools/           # SIL SQLite query engine & rainbow syntax
├── RapscallionSyntax/             # SL4 log syntax and color schemes
├── RapscallionTools/              # Core status bar, media, session, navigation tools
├── RapscallionZip/                # Archive viewer and virtual tree extractor
├── .gitignore                     # Git ignore rules for caches and pycache
├── install.ps1                    # Interactive & CLI PowerShell package installer
└── README.md                      # Suite documentation
```

---

## Installation

### Method 1: Automated Installer (Recommended)

Run the included PowerShell installer from the repository root:

```powershell
# Interactive Selection Menu (pick and choose packages):
.\install.ps1

# Install All Packages via Live Junctions (edits in repo reflect immediately):
.\install.ps1 -All

# Install All Packages via Standalone Copy (independent of repo):
.\install.ps1 -All -Mode Copy

# Install Specific Packages Only:
.\install.ps1 -Packages RapscallionBookmarks,RapscallionNotes

# Uninstall Packages:
.\install.ps1 -All -Uninstall
```

### Method 2: Manual Installation (No Scripts)

1. In Sublime Text 4, open **Preferences > Browse Packages...** to reveal your `Packages` directory (`%APPDATA%\Sublime Text\Packages`).
2. Copy any desired package folder (e.g., `RapscallionBookmarks`) from this repository directly into that folder.
3. Sublime Text will instantly load the package without restarting.

### Method 3: Pre-built `.sublime-package` (GitHub Releases)

1. Download `<PackageName>.sublime-package` from the repository [Releases](https://github.com/Rapscallion0/rapscallion-sublime-tools/releases).
2. Copy the file into `%APPDATA%\Sublime Text\Installed Packages`.

---

## License

Private repository. All rights reserved.
