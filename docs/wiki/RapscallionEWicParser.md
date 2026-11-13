# RapscallionEWicParser

Buypass/FIS, RBSLynk ISO, and WinEPS E-WIC POS log decoder, multi-state TLV unpacker, APL (Approved Product List) catalog cross-referencing, and transaction reconciliation engine.

## Key Features
- **Multi-Format POS Log Decoding**: Supports Buypass/FIS, RBSLynk ISO, WinEPS, and V4 `.sl4` logs.
- **TLV Unpacker**: Decodes nested EMV/WIC Tag-Length-Value payloads cleanly, including malformed-length resilience.
- **APL Catalog Cross-Referencing**: Loads APL catalog files to resolve UPCs and category codes into human-readable product descriptions.
- **Targeted & Full-Log Auditing**: Audit an entire log file or target a single transaction by Invoice, Sequence, or Auth number.
- **Flexible Report Output**: Render audit reports to Markdown, Browser HTML, or both.

## Commands & Shortcuts

| Action | Command Palette (`Ctrl+Shift+P`) | Chord |
| :--- | :--- | :--- |
| Parse Selected Card Balances | `Raps: WIC - Parse Selected Card Balances` | `Ctrl+Alt+W` / `Ctrl+Alt+W, S` |
| Analyze Transaction by ID | `Raps: WIC - Analyze Transaction by Invoice / Sequence / Auth #` | `Ctrl+Alt+W, I` |
| Audit All Transactions in Log | `Raps: WIC - Audit All Transactions in Log` | `Ctrl+Alt+W, A` |
| View Report in Browser | `Raps: WIC - View Report in Browser` | `Ctrl+Alt+W, B` |
| Set Report Output Destination | `Raps: WIC - Set Report Output Destination…` | `Ctrl+Alt+W, D` |
| Load APL Catalog File | `Raps: WIC - Load APL Catalog File…` | `Ctrl+Alt+W, L` |
| Clear Active APL Cache | `Raps: WIC - Clear Active APL Cache` | `Ctrl+Alt+W, C` |
