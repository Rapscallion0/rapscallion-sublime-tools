# Rapscallion Tools - Ticket Notes

Automated ticket notes creation, path matching, and template management for Sublime Text 4.

## Features
- **Auto-Scaffolding:** Automatically creates and opens `.notes.md` inside a project's `.sublime` folder upon opening files matching configured path rules (e.g. `D:\_Calls`).
- **Template Substitution:** Interpolates dynamic variables like `${ticket_number}`, `${date}`, `${time}`, `${tac_name}`, and workstation hostnames.
- **Template Editor Buffer:** Dedicated interactive scratch view for updating default or per-path templates, persisting directly to your settings on save.
