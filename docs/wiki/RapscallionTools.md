# RapscallionTools

Core environment utilities for Sublime Text 4: hex character decoding, status bar file/git metrics, external media routing, folder session management, timestamp insertion, and XML tag jumping.

## Key Features
- **Hex Character Decoder**: Decodes `{HH}`, `%HH`, `\xHH`, or all formats in sequence—either in place or to a new tab.
- **Status Bar Info (`sb_info`)**: Displays file path, git branch, size, permissions, modified time, and optional line count, plus a detailed popup/panel.
- **External Media Routing**: Intercepts binary media files (`.pdf`, `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.wmv`, `.flv`) and opens an interactive preview card + launches the default OS app instead of dumping binary text into Sublime.
- **Folder Session Manager**: Persists and restores open folder sessions (`.sublime/folder-session.json`).
- **Quick Utilities**: Timestamp insertion (full, date, time, ISO UTC), XML matching tag jump, and jump to first match.

## Commands & Shortcuts

| Action | Command Palette (`Ctrl+Shift+P`) | Chord / Shortcut |
| :--- | :--- | :--- |
| Decode Hex (`{0x..}`) In Place | `Raps: Tools - Decode Hex Characters (In Place)` | `Ctrl+Alt+H, B` / `Alt+H` |
| Decode Hex (`{0x..}`) To New Tab | `Raps: Tools - Decode Hex Characters (To New Tab)` | `Ctrl+Alt+H, T` / `Alt+Shift+H` |
| Decode All Hex Formats In Place | `Raps: Tools - Decode Hex Characters (All Formats - In Place)` | `Ctrl+Alt+H, A` |
| Decode All Hex Formats To New Tab | `Raps: Tools - Decode Hex Characters (All Formats - To New Tab)` | `Ctrl+Alt+H, N` |
| Insert Full Timestamp | `Raps: Tools - Insert Timestamp` | `Ctrl+Alt+U, T` / `Shift+F5` |
| Insert Date / Time / ISO UTC | — | `Ctrl+Alt+U, D` / `H` / `I` |
| Jump to Matching XML Tag | `Raps: Tools - Jump to Matching XML Tag` | `Ctrl+Alt+U, X` / `Alt+M` |
| Jump to First Match | `Raps: Tools - Jump to First Match` | `Ctrl+Alt+U, M` / `Ctrl+F3` |
| Toggle Status Bar Info | `Raps: Tools - Toggle Status Bar Info` | `Ctrl+Alt+U, S` |
| Show Status Bar Details | `Raps: Tools - Show Status Bar Info Details` | `Ctrl+Alt+U, P` |
| Restore Folder Session | `Raps: Tools - Restore Folder Session` | — |

## Settings (`RapscallionTools.sublime-settings`)
- `open_external_media_enabled`, `external_media_extensions`, `relaunch_if_already_open`
- `hex_decode_default_pattern` (`"brace"`, `"percent"`, `"escaped"`, `"all"`)
- Status bar toggles (`size`, `permissions`, `modified`, `total_lines`)
