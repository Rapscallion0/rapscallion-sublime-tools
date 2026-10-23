# Rapscallion Tools - SIL Inspector & Query Engine

**RapscallionSILTools** is a self-contained Sublime Text package designed for parsing, inspecting, color-coding, and querying System Integration Language (SIL) database dump files and tabular datasets.

It features synchronized rainbow column highlighting, interactive hover tooltips, live status bar position tracking, non-blocking asynchronous ingestion, automated numeric type inference, a 1-click column frequency analyzer, and an in-memory SQLite query engine capable of parsing single or multi-table SIL dumps and iteratively drilling down into exported CSV result tabs.

---

## Features

* **Synchronized Rainbow Highlighting:** Maps SQL header views (`CREATE VIEW ... AS SELECT ... FROM`) and data rows (`('val1', 'val2', ...)`) to an identical 10-color cycle. Headers and corresponding columns always share matching colors.
* **Lexer-Accurate Parsing:** Stateful tuple lexer safely handles consecutive commas inside quotes, standard SQL escaped quotes (`''`), and empty fields without regex corruption.
* **Dynamic Type Inference:** Automatically detects and applies `INTEGER`, `REAL`, or `TEXT` SQLite affinities from sample data rows, enabling native mathematical comparisons (`WHERE Col > 100`) and numeric sorting without manual `CAST` statements.
* **1-Click Column Frequency Analysis (`Alt + F`):** Instantly analyzes value frequency distributions for the column under your cursor, generating a sorted percentage breakdown in a fresh tab.
* **In-Memory SQLite Query Engine (`Alt + Q`):** Ingests tabular rows into an in-memory SQLite instance, prompts for queries via an auto-completing input panel, and dumps results into a fresh CSV scratch buffer.
* **Context-Aware Field Hover:** Hover over any data value to display its 1-based column number, schema column name, and the field's actual value styled in the column's exact syntax color.
* **Status Bar Column Tracking:** Displays live column indices and header names directly in Sublime Text's status bar as you navigate via keyboard in both SIL dumps and CSV tabs.
* **Iterative Querying (Drill-Down):** Execute queries directly on generated `<Table> Results.csv` tabs. RapscallionSILTools automatically ingests CSV headers and rows into SQLite tables (`<Table>_SUB`), enabling multi-stage data filtering.
* **Non-Blocking Async Ingestion:** Parses large SIL and CSV buffers on a dedicated background worker thread, displaying an animated spinner in the status bar without locking up Sublime Text's UI.

---

## Key Bindings

| Shortcut | Context | Command | Description |
|---|---|---|---|
| `Alt + Q` | SIL view or CSV file | `sil_sqlite_query` | Ingests data and opens the SQLite query input panel |
| `Alt + F` | SIL view or CSV file | `sil_column_frequency` | Runs instant frequency distribution analysis on current column |

---

## Command Palette & Context Menu

Press `Ctrl + Shift + P` and type `Rapscallion Tools: SIL`:

* `Rapscallion Tools: SIL - Query with SQLite` (`Alt + Q`) -- Execute an SQLite query against the active SIL file or CSV tab.
* `Rapscallion Tools: SIL - Frequency Analysis on Column` (`Alt + F`) -- Generate a frequency distribution report for the current column.
* `Rapscallion Tools: SIL - Toggle Field Hover` -- Turn hover inspection popups on or off.
* `Rapscallion Tools: SIL - Settings` -- Open default and user settings side-by-side.
* `Rapscallion Tools: SIL - Documentation` -- Open this documentation directly inside Sublime Text.

You can also right-click anywhere in a SIL or CSV buffer to access these commands directly from the context menu.

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

    // Default template when launching a query. "{table}" will be replaced with the active table name.
    "default_query_template": "SELECT * FROM {table}",

    // Delimiter for query results: "," for CSV, "\t" for TSV
    "export_delimiter": ",",

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
