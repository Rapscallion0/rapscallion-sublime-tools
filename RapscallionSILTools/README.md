# Rapscallion Tools - SIL Inspector & Query Engine

**RapscallionSILTools** is a self-contained Sublime Text package designed for parsing, inspecting, color-coding, formatting, and querying System Integration Language (SIL) database dump files and tabular datasets.

It features synchronized rainbow column highlighting, interactive hover tooltips, live status bar position tracking, non-blocking asynchronous ingestion, automated numeric type inference, a 1-click column frequency analyzer, table column alignment formatting, a dedicated multi-line SQL query scratchpad, analytical query presets, schema inspection, and configurable export to CSV or aligned Markdown tables.

---

## Features

* **Synchronized Rainbow Highlighting:** Maps SQL header views (`CREATE VIEW ... AS SELECT ... FROM`) and data rows (`('val1', 'val2', ...)`) to an identical 10-color cycle. Headers and corresponding columns always share matching colors.
* **Lexer-Accurate Parsing:** Stateful tuple lexer safely handles consecutive commas inside quotes, standard SQL escaped quotes (`''`), and empty fields without regex corruption.
* **Dynamic Type Inference:** Automatically detects and applies `INTEGER`, `REAL`, or `TEXT` SQLite affinities from sample data rows, enabling native mathematical comparisons (`WHERE Col > 100`) and numeric sorting without manual `CAST` statements.
* **Align Table Columns (`Alt + A`):** Vertically formats jagged row tuples or CSV lines into an aligned spreadsheet-like grid directly in your editor. Easily reversible in one step with standard Undo (`Ctrl + Z`).
* **Go to Column N & Schema Inspector (`Alt + G`):** Quickly navigate wide tables (30+ columns) by column number or name. Displays a quick panel with field names and sample values from the current line; selecting any column instantly positions the cursor at that field.
* **Multi-Line SQL Scratchpad (`Ctrl + Alt + Q`):** Opens a dedicated `<Table> Query.sql` scratchpad buffer with full SQL syntax highlighting, code completions, and multi-line formatting. Press `Ctrl + Enter` to execute the entire query or selected block.
* **Query History & Analytical Presets:** Recall recent queries or execute one-click analytical templates (Find Duplicates, Find Nulls, Distinct Value Count, Top 20 Most Frequent, and Numeric Summaries).
* **Configurable Markdown or CSV Results:** Toggle query results between standard CSV (`Results.csv`) and aligned GitHub-Flavored Markdown tables (`Results.md`) via settings or the toggle command.
* **1-Click Column Frequency Analysis (`Alt + F`):** Instantly analyzes value frequency distributions for the column under your cursor, generating a sorted percentage breakdown in a fresh tab.
* **In-Memory SQLite Query Engine (`Alt + Q`):** Ingests tabular rows into an in-memory SQLite instance, prompts for queries via an auto-completing input panel, and dumps results into a fresh scratch buffer.
* **Context-Aware Field Hover:** Hover over any data value to display its 1-based column number, schema column name, and the field's actual value styled in the column's exact syntax color.
* **Status Bar Column Tracking:** Displays live column indices and header names directly in Sublime Text's status bar as you navigate via keyboard in both SIL dumps and CSV tabs.
* **Iterative Querying (Drill-Down):** Execute queries directly on generated `<Table> Results.csv` tabs. RapscallionSILTools automatically ingests CSV headers and rows into SQLite tables (`<Table>_SUB`), enabling multi-stage data filtering.
* **Non-Blocking Async Ingestion:** Parses large SIL and CSV buffers on a dedicated background worker thread, displaying an animated spinner in the status bar without locking up Sublime Text's UI.

---

## Key Bindings & Key Chords

All SIL tools feature unified key chords with prefix **`Ctrl+Alt+S`** (macOS: **`Super+Alt+S`**), alongside direct single-stroke shortcuts:

| Key Chord | Direct Shortcut | Context | Command | Description |
|---|---|---|---|---|
| `Ctrl+Alt+S, Q` | `Alt + Q` | SIL view or CSV file | `sil_sqlite_query` | Ingests data and opens the SQLite query input panel |
| `Ctrl+Alt+S, F` | `Alt + F` | SIL view or CSV file | `sil_column_frequency` | Runs instant frequency distribution analysis on current column |
| `Ctrl+Alt+S, G` | `Alt + G` | SIL view or CSV file | `sil_goto_column` | Opens Column Jump navigator & Schema Inspector |
| `Ctrl+Alt+S, A` | `Alt + A` | SIL view or CSV file | `sil_align_columns` | Vertically aligns table columns across rows (undo with `Ctrl+Z`) |
| `Ctrl+Alt+S, S` | `Ctrl + Alt + Q` | SIL view or CSV file | `sil_open_scratchpad` | Opens dedicated multi-line SQL Query Scratchpad tab |
| `Ctrl+Alt+S, P` | — | SIL view or CSV file | `sil_query_presets` | Opens Query Presets & History panel |
| `Ctrl+Alt+S, R` | — | Anywhere | `sil_toggle_result_format` | Toggles query result format between CSV and Markdown |
| `Ctrl+Alt+S, H` | — | Anywhere | `sil_toggle_hover` | Toggles field hover inspect tooltips |
| `Ctrl+Alt+S, D` | — | Anywhere | `sil_show_docs` | Opens this package README documentation |
| — | `Ctrl + Enter` | In SQL Scratchpad | `sil_execute_scratchpad` | Executes active query or selected text and opens results |

---

## Command Palette & Context Menu

Press `Ctrl + Shift + P` and type `Rapscallion Tools: SIL`:

* `Rapscallion Tools: SIL - Query with SQLite` (`Alt + Q`)
* `Rapscallion Tools: SIL - Frequency Analysis on Column` (`Alt + F`)
* `Rapscallion Tools: SIL - Go to Column / Schema Inspector` (`Alt + G`)
* `Rapscallion Tools: SIL - Align Table Columns` (`Alt + A`)
* `Rapscallion Tools: SIL - Open SQL Query Scratchpad` (`Ctrl + Alt + Q`)
* `Rapscallion Tools: SIL - Query Presets & History`
* `Rapscallion Tools: SIL - Toggle Result Format (CSV / Markdown)`
* `Rapscallion Tools: SIL - Toggle Field Hover`
* `Rapscallion Tools: SIL - Settings`
* `Rapscallion Tools: SIL - Documentation`

Right-clicking anywhere inside a SIL dump or CSV results buffer will also display these contextual commands.

---

## Configuration

Settings can be customized via **Preferences > Package Settings > Rapscallion Tools > SIL Query & Inspector > Settings** or by editing `Packages/User/RapscallionSILTools.sublime-settings`:

```json
{
    // Enable or disable hover inspection tooltips
    "hover_enabled": true,

    // Show hovered field value below the column name
    "hover_show_value": true,

    // Maximum character length for values in tooltips before truncating (0 for no limit)
    "hover_max_value_length": 80,

    // Show current column position and header name in the status bar at the cursor position
    "status_bar_column_info": true,

    // Parse files and initialize SQLite on a background worker thread
    "async_ingestion": true,

    // Batch size (rows) when inserting data into SQLite
    "ingestion_batch_size": 5000,

    // Number of sample rows inspected to infer SQLite data types (0 = all TEXT)
    "type_inference_sample_size": 100,

    // Multi-table behavior: "prompt", "all_silent", or "first"
    "multi_table_behavior": "prompt",

    // Default output format for queries: "csv" or "markdown"
    "default_result_format": "csv",

    // Default template when launching a query. "{table}" will be replaced with the active table name.
    "default_query_template": "SELECT * FROM {table}",

    // Delimiter for query results: "," for CSV, "\t" for TSV
    "export_delimiter": ",",

    // Maximum character width for any single column when aligning (0 = unlimited)
    "align_max_col_width": 120,

    // Preferred syntax path for result buffers (leave empty for auto-detection)
    "preferred_csv_syntax": ""
}
```

---

## Installation

### Automated (PowerShell)
From the repository root, run:
```powershell
.\install.ps1 -Packages RapscallionSILTools
```

### Manual
Copy this `RapscallionSILTools` folder into your Sublime Text `Packages` directory (accessible via **Preferences > Browse Packages...**).
