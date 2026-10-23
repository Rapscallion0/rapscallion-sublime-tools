# Rapscallion Tools - SIL Inspector & Query Engine

**RapscallionSILTools** is a self-contained Sublime Text package designed for parsing, inspecting, color-coding, and querying System Integration Language (SIL) database dump files and tabular datasets.

It features synchronized rainbow column highlighting, interactive hover tooltips, live status bar position tracking, non-blocking asynchronous ingestion, and an in-memory SQLite query engine capable of parsing single or multi-table SIL dumps and iteratively drilling down into exported CSV result tabs.

---

## Features

* **Synchronized Rainbow Highlighting:** Maps SQL header views (`CREATE VIEW ... AS SELECT ... FROM`) and data rows (`('val1', 'val2', ...)`) to an identical 10-color cycle. Headers and corresponding columns always share matching colors.
* **Context-Aware Field Hover:** Hover over any data value to display its 1-based column number, schema column name, and the field's actual value styled in the column's exact syntax color.
* **Status Bar Column Tracking:** Displays live column indices and header names directly in Sublime Text's status bar as you navigate via keyboard.
* **Non-Blocking Async Ingestion:** Parses large SIL and CSV buffers on a dedicated background worker thread, displaying an animated spinner in the status bar without locking up Sublime Text's UI.
* **Multi-Table SIL Support:** Automatically detects multiple `CREATE VIEW` declarations within a single dump file. Allows selecting a primary target table via a Quick Panel while keeping all tables available for cross-table SQL joins in memory.
* **In-Memory SQLite Query Engine:** Ingests tabular rows into an in-memory SQLite instance, prompts for queries via an auto-completing input panel, and dumps results into a fresh CSV scratch buffer.
* **Iterative Querying (Drill-Down):** Execute queries directly on generated `<Table> Results.csv` tabs. RapscallionSILTools automatically ingests CSV headers and rows into SQLite tables (`<Table>_SUB`), enabling multi-stage data filtering.
* **Robust Literal & Escape Handling:** Correctly handles standard SQL escaped quotes (`''`) without breaking sequence contexts or drifting rainbow column colors.
* **Fully Decoupled:** Eliminates external dependencies on third-party Rainbow CSV packages by utilizing standard TextMate scope mappings alongside dynamic theme color extraction.

---

## Key Bindings

| Shortcut | Context | Description |
|---|---|---|
| `Alt + Q` | SIL buffer (`.sil`, `@CREATE`, `CREATE VIEW`) or CSV files | Ingests data and opens the SQLite query input panel |

---

## Command Palette

Press `Ctrl + Shift + P` (or `Cmd + Shift + P` on macOS) and type `RapscallionSILTools:`:

* `RapscallionSILTools: Query with SQLite` -- Execute an SQLite query against the active SIL file or CSV tab.
* `RapscallionSILTools: Toggle Field Hover` -- Turn hover inspection popups on or off.
* `RapscallionSILTools: Settings` -- Open default and user settings side-by-side.
* `RapscallionSILTools: Documentation` -- Open this documentation directly inside Sublime Text.

---

## Configuration

Settings can be customized via **Preferences > Package Settings > RapscallionSILTools > Settings** or by editing `Packages/User/RapscallionSILTools.sublime-settings`.

### RapscallionSILTools.sublime-settings

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

### Settings Reference

| Setting | Type | Default | Description |
|---|---|---|---|
| `hover_enabled` | `boolean` | `true` | Master toggle for column inspection tooltips on data lines. |
| `hover_show_value` | `boolean` | `true` | Toggles whether the hovered cell's value appears in the tooltip. |
| `hover_max_value_length` | `integer` | `80` | Limits character count for large fields in popups (appends `...` when exceeded). Set to `0` to disable truncation. |
| `status_bar_column_info` | `boolean` | `true` | Displays active column number and column header in the Sublime Text status bar. |
| `async_ingestion` | `boolean` | `true` | Runs file parsing and SQLite database ingestion on a background thread. |
| `ingestion_batch_size` | `integer` | `5000` | Number of rows chunked per insertion batch during SQLite setup. |
| `type_inference_sample_size` | `integer` | `100` | Sample size for schema typing. Set to `0` to treat all columns as raw `TEXT`. |
| `multi_table_behavior` | `string` | `"prompt"` | Handling when multiple tables exist: `"prompt"` (quick-panel selection), `"all_silent"` (load all, target first), or `"first"` (load first only). |
| `default_query_template` | `string` | `"SELECT * FROM {table}"` | Initial query loaded into the input panel (`{table}` auto-resolves to the active table name). |
| `export_delimiter` | `string` | `","` | Field separator character used when writing query results to scratch tabs. |
| `preferred_csv_syntax` | `string` | `""` | Explicit `.sublime-syntax` path for result buffers. If empty, auto-detects installed Rainbow CSV grammars before falling back to `text.csv`. |

---

## File Format Support

### 1. SIL Database Dumps

Recognized by the `.sil` extension, `@CREATE(...)` batch markers, or `CREATE VIEW ... AS SELECT ... FROM` declarations:

```sql
@CREATE(BMP_TAB,BMP);
CREATE VIEW BMP_Load AS SELECT F01,F2926,F2927,F2928,F253,F1001,F2929 FROM BMP_TAB;

INSERT INTO BMP_Load VALUES
('0000000004011','MAIN','MAIN','THUMB','2026231 16:49:19',1,'0000000004011.bmp'),
('0005574200568','MAIN','MAIN','THUMB','2026231 16:49:19',1,'0005574200568.BMP');
```

* **Table Detection:** Automatically extracts view names (e.g., `BMP_Load`). Multi-table files are supported.
* **Column Mapping:** Extracts all columns after `SELECT` and handles unquoted null fields (`,,`) automatically during database ingestion.
* **SQL Dialect:** Uses standard native SQLite syntax (`IFNULL(col, alt)`, `COALESCE(...)`, `WHERE col IS NULL`).

### 2. CSV Result Buffers

Any tab ending in `.csv` or named `<Table> Results.csv` can be queried directly using standard SQLite SQL syntax (`WHERE`, `ORDER BY`, `GROUP BY`, joins, aggregations).

---

## Package File Layout

```text
Packages/RapscallionSILTools/
├── Default (Windows).sublime-keymap     # Alt+Q binding
├── Default.sublime-commands             # Unified RapscallionSILTools: command palette list
├── Main.sublime-menu                    # Preferences > Package Settings integration
├── README.md                            # Documentation
├── SIL (Rainbow).sublime-syntax         # 10-column rainbow syntax grammar
├── SIL.sublime-color-scheme             # 10-color rainbow palette definitions
├── RapscallionSILTools.sublime-settings            # Default configuration
├── sil_field_hover.py                   # Hover tooltip & status bar column tracker
├── sil_sqlite_query.py                  # In-memory SQLite async engine & CSV exporter
└── sil_syntax_detector.py               # Auto-assign syntax on load/save & show docs
```