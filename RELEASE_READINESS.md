# Release Readiness Gaps

This file tracks the practical gaps between the current local app and a wider, robust release.

## Addressed Now

- Tests: added `tests/` with unit coverage for schema/versioning, backup/export, support bundles, UI accessibility, keyboard entry points, the day score query, and router classifier caching.
- Hot-path query: `Repository.day_scores()` now batches daily task rows across the requested range instead of querying once per day.
- Router latency: `ContextRouter` caches `TinyIntentClassifier` until capture/correction data changes.
- ML cold start: `LocalIntentModel` now warms in a background thread and returns to rules/memory while the model is loading.
- Logging: startup config writes a rotating local log at `logs/momentum.log`; previously swallowed migration, FTS, and ML failures are now logged.
- Data safety: SQLite now has a `schema_version` table plus backup, restore, and SQL export helpers.
- Accessibility: the capture window now sets accessible names/descriptions and keyboard focus policy on the main capture, notebook, sidebar, library actions, search, inbox, summary range, and key buttons.
- Local artifact hygiene: logs, backups, exports, datasets, checkpoints, model files, root screenshots, and design scratch files are ignored by Git.

## Remaining Gaps

### UI Architecture

`momentum/ui/capture_window.py` has been reduced to the window coordinator. Capture UI pieces now live in focused modules:

```text
momentum/ui/capture/sidebar.py
momentum/ui/capture/editor.py
momentum/ui/capture/cards.py
momentum/ui/capture/dialogs.py
momentum/ui/capture/utils.py
momentum/ui/capture/accessibility.py
```

Remaining cleanup: move the remaining `CaptureWindow` orchestration methods into smaller application services once behavior is covered by deeper UI tests.

### Test Depth

Current tests protect the highest-risk internals and a basic UI smoke path. A stronger release should add:

- UI smoke tests for capture save, delete, restore, theme switch, and note autosave.
- Migration tests for realistic `daily_focus.json`.
- Router tests for explicit prefixes, date parsing, corrections, and low-confidence inbox flow.
- Export tests for weekly summaries and engineering reports.

### Packaging

The current `.bat` scripts are good for local builds. The repo now also includes a local Windows package flow:

```powershell
.\scripts\package_windows_release.ps1
```

The package includes `MomentumCapture.exe`, install/uninstall scripts, docs, and a SHA-256 checksum. A public Windows release still needs:

- signed executable or installer
- code-signing certificate
- auto-update strategy
- versioned release notes

### Accessibility

Accessible names are now present on the main controls, but a full pass should verify screen-reader order, contrast, keyboard-only navigation, and focus visibility with real assistive tooling.

### Observability

Local logging exists now. The Reports tab can create a support bundle that exports:

- `logs/momentum.log`
- app version
- schema version
- OS/Python/runtime information
- redacted recent error traces

### Data Safety

Database backup/export helpers exist, and the Reports tab exposes:

- Create Backup
- Export Database
- Support Bundle
- Open Data Folder

Remaining cleanup: add restore backup as a guarded Settings action that first creates a fresh automatic backup.
