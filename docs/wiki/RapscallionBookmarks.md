# RapscallionBookmarks

Visual bookmark manager for Sublime Text 4 featuring a Quick Panel with live scrolling preview, an interactive HTML Side Panel (`HtmlSheet`), a bottom dock output panel, gutter icons, and Markdown export.

## Key Features
- **Project-Scoped Persistence**: Stores bookmarks per workspace in `<project_root>/.sublime/RapscallionBooks.json` with automatic line-drift tracking.
- **Interactive HTML Side Panel**: Tree view grouped by file with one-click jump, rename, delete, expand/collapse all, and automatic layout collapse when the panel is closed.
- **Quick Panel Navigator**: Fuzzy-search bookmarks across the file or project with live viewport preview as you arrow through entries.
- **Bottom Dock Panel**: Keyboard-driven panel (`Enter` jump, `R` rename, `T` set tag/category, `Delete` remove, `F5` refresh).
- **Markdown Export**: Exports all project bookmarks into a structured Markdown document.

## Commands & Shortcuts

| Action | Command Palette (`Ctrl+Shift+P`) | Chord / Shortcut |
| :--- | :--- | :--- |
| Toggle Bookmark | `Raps: Bookmarks - Toggle Bookmark` | `Ctrl+Alt+B, T` / `Ctrl+F2` |
| Add Named Bookmark | `Raps: Bookmarks - Add Named Bookmark…` | `Ctrl+Alt+B, N` / `Ctrl+Shift+F2` |
| Quick Panel (Jump / Search) | `Raps: Bookmarks - Quick Panel (Jump / Search)` | `Ctrl+Alt+B, Q` / `Alt+B` |
| Next / Previous in File | `Raps: Bookmarks - Next / Previous Bookmark in File` | `F2` / `Shift+F2` |
| Next / Previous in Project | `Raps: Bookmarks - Next / Previous Bookmark in Project` | `Alt+F2` / `Alt+Shift+F2` |
| Toggle Bottom Panel | `Raps: Bookmarks - Toggle Bookmarks Panel` | `Ctrl+Alt+B, P` / `Alt+Shift+B` |
| Toggle Side Panel (HTML Sheet) | `Raps: Bookmarks - Toggle Side Panel (HTML Sheet)` | — |
| Clear Bookmarks in File | `Raps: Bookmarks - Clear Bookmarks in This File` | `Ctrl+Alt+B, C` |
| Export Bookmarks to Markdown | `Raps: Bookmarks - Export Bookmarks to Markdown` | `Ctrl+Alt+B, E` |
| Clean Missing / Dead Bookmarks | `Raps: Bookmarks - Clean Missing / Dead Bookmarks` | — |
