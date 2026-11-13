# RapscallionNotes

Instant project scratchpad and Markdown notes manager with path-based rules and a template editor.

## Key Features
- **Project-Scoped Notes**: Automatically creates or opens a project note file (default `<project_root>/.sublime/.notes.md`) when working inside matched folders.
- **Path Rules (`notes_path_rules`)**: Configure custom `path_prefix`, `filename`, `subfolder`, and `template` per workspace/directory tree.
- **Dynamic Template Variables**: Supports `${folder_name}`, `${date}`, `${time}`, `${user}`, `${ticket_number}`, and `${tac_name}`.
- **Interactive Template Editor**: Opens a tagged scratch buffer where `Ctrl+S` commits the updated template directly into `RapscallionNotes.sublime-settings` instead of writing a temp file to disk.

## Commands & Shortcuts

| Action | Command Palette (`Ctrl+Shift+P`) | Chord |
| :--- | :--- | :--- |
| Create or Open Note | `Raps: Notes - Create or Open Note` | `Ctrl+Alt+N, C` / `Ctrl+Alt+N, N` |
| Edit Note Template | `Raps: Notes - Edit Template` | `Ctrl+Alt+N, T` |

## Settings (`RapscallionNotes.sublime-settings`)
- `notes_auto_open` (default `true`)
- `notes_auto_create_outside_rules` (default `false`)
- `notes_subfolder` (default `".sublime"`)
- `notes_default_filename` (default `".notes.md"`)
- `default_tac_name`, `notes_default_template`, `notes_path_rules`
