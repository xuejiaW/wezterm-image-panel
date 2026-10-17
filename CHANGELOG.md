# Changelog

## 0.4.0 — WezTerm Image Panel / native Windows

- Adopt the WezTerm Image Panel project, package, and command names.
- Add native Windows console input, immediate extended-arrow decoding, virtual
  terminal output, and system image opening.
- Identify local Windows Codex processes through CIM, and normalize Windows
  file URLs and extended paths before comparing session directories.
- Make the Lua integration work without the debug library; configure its source
  root or executable explicitly. Add a Windows shortcut example.
- Exercise real Codex image logs and WezTerm control paths; document separately
  what was automated and what still needs visual or platform validation.

## 0.3.0 — Public repository preparation

- Replace machine-specific instructions with reproducible installation and
  configurable WezTerm shortcut setup.
- Exclude personal recordings, diagnostics, sessions, and original local
  material from Git and source distributions.
- Add an offline demo with original generated test cards.
- Close read-only SQLite connections after session identification.
- Allow headless parser tests on Windows while reporting native viewer limits.
- Add release checks, packaging validation, and a headless CI workflow.

## 0.2.1 — Local prototype

Image extraction, gallery navigation, incremental updates, terminal resize
handling, and local macOS shortcut integration were implemented and exercised
locally. Personal recordings from that phase are not public release assets.
