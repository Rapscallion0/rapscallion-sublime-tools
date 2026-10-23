# Rapscallion Tools - Core Suite

Essential editor utilities, session management, media preview routing, and navigation helpers for Sublime Text 4.

---

## Features

### Dynamic Status Bar (`status_bar_info.py`)
- Real-time buffer and filesystem telemetry: Read-only status (`[RO]`), character encoding, line endings (CRLF/LF), file size on disk, permissions, modification timestamp, and total line counts.
- **Detailed Metrics Popup:** Interactive pop-up dialog (`rapscallion_show_status_details`) displaying expanded file attributes with theme-aware styling.
- **Toggle Control:** Quickly toggle status bar reporting via the Command Palette or application menu.

### External Media Routing (`open_external_media.py`)
- Automatically intercepts binary media documents (`.pdf`, `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, etc.) opened in Sublime Text.
- Generates a styled, interactive HTML phantom preview card inside Sublime with file metadata and one-click actions:
  - *Re-open in External App*
  - *Open Folder / Reveal in Explorer*
  - *Copy File Path*
- Spawns the default OS system application in a detached background process.

### Project Folder Sessions (`folder_session_manager.py`)
- Automatically preserves open tabs, cursor selection regions, and viewport scroll positions per project folder under `.sublime/folder-session.json`.
- Restores project window state on workspace launch without corrupting temporary buffers.

### Micro Navigation & Editing Shortcuts
- **Jump to First Match (`jump_to_first_match.py`):** Shifts focus and positions cursor at match position 0 (`Ctrl+F3`).
- **XML Tag Jumper (`jump_xml_tag.py`):** Structural traversal between opening and closing tags in XML/HTML (`Alt+M`).
- **Timestamp Insertion (`insert_timestamp.py`):** Fast insertion of ISO timestamps or date-only stamps (`Shift+F5`, `Ctrl+Shift+F5`).

---

## Configuration

Settings can be customized via **Preferences > Package Settings > Rapscallion Tools > Core Settings** or by editing:
`Packages/User/RapscallionTools.sublime-settings`