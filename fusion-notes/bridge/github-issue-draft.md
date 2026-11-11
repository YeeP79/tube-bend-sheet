Hi Frank, thanks for this project. I've been using it daily on a large multi-part design and built a set of additions on a fork. Each one is its own branch off `main`, with unit tests, and most have been run in live Fusion on macOS (status below).

One is a bug fix I can send right away: on MCP 2026-07-28, every tool call fails with `-32603` once Fusion passes 1024 open files, because `select.select` raises `ValueError` in `_client_disconnected`.

There are 26 new tools plus a few improvements, so before I open anything: would you prefer small PRs one at a time, a few grouped PRs, or only the ones that fit your scope? Happy to leave out anything you'd rather not take. Some are Personal Use specific.

### Modeling and geometry

| Tool | What it does | Live tested |
| --- | --- | --- |
| `compute` | Runs Fusion's real Compute All and reports timeline health | Yes |
| `timeline_health` | Lists broken timeline items, a rolled-back marker and the active component | Report yes; suppressing items and the rollback message not yet |
| `delete_features` | Deletes timeline items by name, with a dry run and dependents | Partly; plan fix in progress |
| `sketch_profile` | Builds closed outlines with shared corner points, refuses self-crossing shapes, inspects profiles | Yes |
| `parameters` | Lists parameters and what each drives; sets them with a dry run | Yes |
| `list_bodies` | Every body in world coordinates; skips hidden bodies by default | Yes |
| `describe_body` | Breaks a body into faces: bore or boss, fillet hints, creating feature | Yes |
| `check_solids` | Checks validity, overlaps, and before/after volume changes | Yes |

### Documents

| Tool | What it does | Live tested |
| --- | --- | --- |
| `document_status` | Open files with version, read-only and unsaved state, and duplicate copies | Yes |
| `activate_document` | Switches the active document by name or id | Not yet |
| `open_document` | Opens a file, reusing an open tab if there is one | Yes |
| `save_document` | Saves and confirms the new version reached the cloud (`save()` can return True while nothing uploads) | Yes |
| `document_versions` | Lists version history | Yes |
| `restore_version` | Promotes an older version and reopens it | Yes |

### Cloud files

| Tool | What it does | Live tested |
| --- | --- | --- |
| `project_tree` | Folder tree with versions, duplicates, and links as full paths | Yes |
| `editable_files` | Personal Use: editable count against the limit, with hints on what's safe to release | Yes |
| `set_editable_state` | Makes files read-only or editable | Yes, both directions |
| `move_files` | Moves files with a dry run and a before/after link check | Yes |
| `rename_file` | Renames a file and confirms the name took | Yes |
| `rename_folder` | Renames a folder, with a two-step path for capitalization-only changes | Partly; capitalization path fix in progress |
| `delete_files` | Permanently deletes files, parents first, with the server's reason for a refusal | Yes |
| `remove_empty_folders` | Removes empty folders, deepest first | Dry run only |

### Bridge

| Tool | What it does | Live tested |
| --- | --- | --- |
| `fusion_dialogs` | macOS: finds and dismisses blocking dialogs while the main thread is stuck; Cancel, Close or Escape only | Yes |
| `tail_log` | Reads Fusion's application log without touching the main thread | Yes |
| `bridge_info` | Running code versus what's on disk | Yes |
| `reload_addin` | Reloads the add-in in place, with no restart | Yes |

### Improvements to existing behavior

| Change | What it does | Live tested |
| --- | --- | --- |
| `clean_view` on `capture_viewport` | Hides sketches and construction geometry for the capture, then restores them | Yes |
| `execute_python` sessions | Imports and functions survive between calls | Yes |
| `select` fix | Tool calls keep working past 1024 open files | Yes |
