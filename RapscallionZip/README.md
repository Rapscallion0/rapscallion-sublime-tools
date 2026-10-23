# Rapscallion Tools - Archive Explorer (Zip)

Interactive archive inspection, navigation, and extraction for Sublime Text 4.

## Features
- **Virtual Tree View:** Browse compressed archive files (`.zip`, `.jar`, `.war`, `.nupkg`) as an interactive ASCII tree.
- **Custom Syntax Coloring:** Highlights archive headers, size metrics, dates, and tree indicators (`RapscallionZip.sublime-syntax`).
- **Interactive Navigation:** Single-click to toggle directories, double-click or `Enter` to extract and open individual files in scratch buffers.
- **Async & Secure Extraction:** Offloads decompression to background worker threads with built-in path-traversal (Zip-Slip) guards.
- **Live Search Filtering:** Press `Ctrl+F` inside an archive buffer to filter files matching keywords.
