# Rapscallion Tools - Ticket Notes

Automated ticket notes creation, path matching, and template management for Sublime Text 4.

## Features
- **Auto-Scaffolding:** Automatically creates and opens `.notes.md` inside a project's `.sublime` folder upon opening files matching configured path rules (e.g. `D:\_Calls`).
- **Template Substitution:** Interpolates dynamic variables like `${ticket_number}`, `${date}`, `${time}`, `${tac_name}`, and workstation hostnames.
- **Template Editor Buffer:** Dedicated interactive scratch view for updating default or per-path templates, persisting directly to your settings on save.

## Key Chords & Shortcuts

Prefix: **`Ctrl+Alt+N`** (macOS: **`Super+Alt+N`**)

| Key Chord | Command | Action |
| :--- | :--- | :--- |
| `Ctrl+Alt+N, C` | `create_ticket_note` | Create or open ticket note for active path |
| `Ctrl+Alt+N, N` | `create_ticket_note` | Create or open ticket note (alias) |
| `Ctrl+Alt+N, T` | `edit_rapscallion_template` | Open interactive template editor buffer |

Customize keybindings via **Preferences > Package Settings > Rapscallion Tools > Ticket Notes > Key Bindings**.

## Installation

### Automated (PowerShell)
From the repository root, run:
```powershell
.\install.ps1 -Packages RapscallionNotes
```

### Manual
Copy this `RapscallionNotes` folder into your Sublime Text Packages directory (accessible via **Preferences > Browse Packages...**).
