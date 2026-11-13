# RapscallionSILTools

In-memory SQLite query engine, synchronized 10-column rainbow syntax highlighter, field hover inspector, and table column aligner for SIL database dumps and CSV logs.

## Key Features
- **SQLite Query Engine**: Streams large SIL/CSV files into an in-memory `sqlite3` database on a background thread with animated progress indicators (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) and outputs results as CSV or Markdown tables.
- **SQL Query Scratchpad**: Dedicated interactive SQL scratchpad buffer (`Ctrl+Enter` to execute) plus saved query presets & history.
- **Field Hover Inspector**: Hovering over any field highlights/identifies the exact column name and index across multi-table SIL dumps.
- **Column Frequency & Go-To**: Quick frequency distribution analysis and jump-to-column schema inspector.
- **Table Aligner**: Aligns delimited SIL/CSV columns cleanly for readability.

## Commands & Shortcuts

| Action | Command Palette (`Ctrl+Shift+P`) | Chord / Shortcut |
| :--- | :--- | :--- |
| Query with SQLite | `Raps: SIL - Query with SQLite` | `Ctrl+Alt+I, Q` / `Alt+Q` |
| Column Frequency Analysis | `Raps: SIL - Frequency Analysis on Column` | `Ctrl+Alt+I, F` / `Alt+F` |
| Go to Column / Schema | `Raps: SIL - Go to Column / Schema Inspector` | `Ctrl+Alt+I, G` / `Alt+G` |
| Align Table Columns | `Raps: SIL - Align Table Columns` | `Ctrl+Alt+I, A` / `Alt+A` |
| Open SQL Query Scratchpad | `Raps: SIL - Open SQL Query Scratchpad` | `Ctrl+Alt+I, S` / `Ctrl+Alt+Q` |
| Execute Scratchpad | — | `Ctrl+Enter` *(in scratchpad)* |
| Query Presets & History | `Raps: SIL - Query Presets & History` | `Ctrl+Alt+I, P` |
| Toggle Result Format | `Raps: SIL - Toggle Result Format (CSV / Markdown)` | `Ctrl+Alt+I, R` |
| Toggle Field Hover | `Raps: SIL - Toggle Field Hover` | `Ctrl+Alt+I, H` |
| Documentation | `Raps: SIL - Documentation` | `Ctrl+Alt+I, D` |
