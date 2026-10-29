# Rapscallion Tools - Core Suite

Essential editor utilities, session management, media preview routing, navigation helpers, and hex decoding for Sublime Text 4.

---

## Features

### Hex Character Decoder (`decode_hex.py` & `tools/decode_hex.py`)
- **Smart Byte Decoding:** Automatically restores hex-escaped characters (such as `{3A}` $\to$ `:`, `{7C}` $\to$ `|`, `{22}` $\to$ `"`, `{2E}` $\to$ `.`) common in POS systems, debug dumps, and telemetry logs.
- **Multi-Byte UTF-8 Support:** Groups consecutive byte sequences (e.g. `{C3}{A9}` $\to$ `é`) to decode valid multi-byte unicode characters without truncation.
- **Selection or Buffer Scope:**
  - When text is selected, decodes only highlighted region(s).
  - When no text is selected, decodes the entire buffer.
- **In-Place or Scratch Tab:**
  - **In-Place (`Alt+H`):** Replaces encoded characters in the current buffer with a single undo step (`Ctrl+Z`).
  - **To New Tab (`Alt+Shift+H`):** Duplicates the decoded content into a new unsaved scratch tab (`[Decoded - ...]`) to leave the original raw log intact.
- **Context & Command Palette Integration:** Accessible via right-click editor context menu and the Command Palette (`Rapscallion Tools: Decode Hex Characters...`).
- **Standalone CLI Tool (`tools/decode_hex.py`):** Can be used directly from PowerShell/Terminal, via standard input stream piping, file paths, or Windows clipboard (`--clipboard`, `--clipboard-out`).

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
- **Hex Decoder In-Place (`Alt+H`):** Decodes `{HH}` tokens in selection or full buffer.
- **Hex Decoder to New Tab (`Alt+Shift+H`):** Decodes `{HH}` tokens into a new scratch tab.
- **Jump to First Match (`Ctrl+F3`):** Shifts focus and positions cursor at match position 0 (`jump_to_first_match.py`).
- **XML Tag Jumper (`Alt+M`):** Structural traversal between opening and closing tags in XML/HTML (`jump_xml_tag.py`).
- **Timestamp Insertion (`Shift+F5`, `Ctrl+Shift+F5`):** Fast insertion of ISO timestamps or date-only stamps (`insert_timestamp.py`).

---

## Configuration

Settings can be customized via **Preferences > Package Settings > Rapscallion Tools > Core Settings** or by editing:
`Packages/User/RapscallionTools.sublime-settings`

Key options for hex decoding:
```json
// Default pattern mode: "brace" ({HH}), "percent" (%HH), "escaped" (\xHH), or "all"
"hex_decode_default_pattern": "brace"
```

---

## Installation

### Automated (PowerShell)
From the repository root, run:
```powershell
.\install.ps1 -Packages RapscallionTools
```

### Manual
Copy this `RapscallionTools` folder into your Sublime Text Packages directory (accessible via **Preferences > Browse Packages...**).
