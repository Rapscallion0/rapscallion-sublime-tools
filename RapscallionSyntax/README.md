# Rapscallion Tools - Syntax Definitions

Custom syntax highlighting grammar definitions for domain-specific languages and SQL dialects in Sublime Text 4.

---

## Included Syntaxes

### LOC (`LOC.sublime-syntax`)
- Syntax definition for LOC SQL macros and directives (`.sqi`, `.sqm`, `.sql`).
- Embedded SQL block parsing (`CREATE TABLE`, `DECLARE`, `BEGIN ... END`).
- Scoping for macro accessors, wizard control directives (`@WIZRPL`, `@WIZSET`, `@IMPORT_SIL`), and field identifiers (`F1000`).

## Installation

### Automated (PowerShell)
From the repository root, run:
`powershell
.\install.ps1 -Packages RapscallionSyntax
`

### Manual
Copy this RapscallionSyntax folder into your Sublime Text Packages directory (accessible via **Preferences > Browse Packages...**).
