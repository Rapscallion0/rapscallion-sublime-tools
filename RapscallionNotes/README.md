# Rapscallion Tools - Notes & Scratchpad

Automated project notes creation, per-folder path rules, and template management for Sublime Text 4.

## Features
- **Works in Any Open Folder:** Manually create or open a note (`.notes.md` by default) in **any** open folder or active file's directory using the global default template—even outside configured `notes_path_rules`.
- **Auto-Scaffolding for Matched Paths:** Automatically creates and opens notes inside configured paths (e.g. `D:\_Calls`) when opening files, with an optional `"notes_auto_create_outside_rules"` setting to enable auto-creation everywhere.
- **Per-Folder Templates, Filenames & Subfolders:** Bind different directory prefixes in `notes_path_rules` to custom filenames (e.g., `NOTES.md`, `.notes.md`), subfolders (e.g., `.sublime`, `docs`, or `""` for folder root), and templates. Longest matching path prefix wins.
- **Template Substitution:** Interpolates dynamic variables like `${folder_name}`, `${ticket_number}`, `${folder_path}`, `${date}`, `${time}`, `${tac_name}`, `${user}`, and `${workstation}`.
- **Template Editor Buffer:** Dedicated interactive scratch view (`edit_rapscallion_template`) for creating path rules and updating default or per-path templates directly on save.

## Key Chords & Shortcuts

Prefix: **`Ctrl+Alt+N`** (macOS: **`Super+Alt+N`**)

| Key Chord | Command | Action |
| :--- | :--- | :--- |
| `Ctrl+Alt+N, C` | `create_note` | Create or open note for active folder |
| `Ctrl+Alt+N, N` | `create_note` | Create or open note (alias) |
| `Ctrl+Alt+N, T` | `edit_rapscallion_template` | Open interactive template editor / add path rule |

Customize keybindings via **Preferences > Package Settings > Rapscallion Tools > Notes & Scratchpad > Key Bindings**.

## Installation

### Automated (PowerShell)
From the repository root, run:
```powershell
.\install.ps1 -Packages RapscallionNotes
```

### Manual
Copy this `RapscallionNotes` folder into your Sublime Text Packages directory (accessible via **Preferences > Browse Packages...**).
