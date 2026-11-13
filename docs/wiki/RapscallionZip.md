# RapscallionZip

Safe, read-only archive inspector and virtual file navigator for `.zip`, `.jar`, `.war`, and `.nupkg` archives.

## Key Features
- **Virtual Tree Explorer**: Inspects archive contents in a tagged read-only scratch buffer (`is_rapscallion_zip_view`) without polluting your workspace.
- **On-Demand File Viewing**: Press `Enter` (or double-click) on any entry to stream and preview its contents safely.
- **Live Tree Filtering**: Filter large archives interactively with `Ctrl+F` inside the archive view.
- **Configurable Guardrails**: Ignores noise patterns (`__MACOSX/*`, `*.DS_Store`, `Thumbs.db`) and enforces `max_extract_size_mb` (default `100` MB).

## Commands & Shortcuts

| Action | Command Palette (`Ctrl+Shift+P`) | Chord / Shortcut |
| :--- | :--- | :--- |
| Filter Current Archive Tree | `Raps: Zip - Filter Current Archive Tree` | `Ctrl+Alt+Z, F` / `Ctrl+F` *(in zip view)* |
| Open Selected Archive Item | — | `Enter` *(in zip view)* |
| Extract Archive to Folder | `Raps: Zip - Extract Archive to Folder` | — |
| Clear Extracted Cache | `Raps: Zip - Clear Extracted Cache` | `Ctrl+Alt+Z, C` |
