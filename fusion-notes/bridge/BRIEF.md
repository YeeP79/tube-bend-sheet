# Bridge feature brief (shared by every feature agent)

Repo: the user's fork of frankhommers/autodesk-fusion-mcp, a Fusion 360 add-in that serves an MCP
server. Main checkout: `~/Projects/personal/fusion/add-ins/AutodeskFusionMCP` (do NOT touch it; it is
the live add-in). You work ONLY in your own worktree under `~/Projects/personal/fusion/bridge-worktrees/<branch>`,
already created on your branch off `main`.

## Rules
- Do not call the live Fusion bridge (no `mcp__autodesk-fusion-mcp__*` tools, nothing on 127.0.0.1:8765).
  There is one Fusion session and it belongs to the user. Unit tests only.
- Do not push, do not open PRs, do not touch other branches or worktrees.
- Commits: conventional style matching history (`feat: ...`, `fix: ...`), a short body explaining why.
  **No trailers of any kind** (no Co-Authored-By, no "Generated with"). A commit-msg hook rejects them.
  Commits are ssh-signed automatically; that works non-interactively.
- One feature per branch. Keep the diff focused; no drive-by refactors.
- Match the surrounding code: comment density, naming, error shape, no new dependencies
  (the add-in runs inside Fusion's bundled CPython 3.14, stdlib only).

## How a tool is added (follow the existing pattern; `compute` on branch `compute-all` is a worked example:
`git -C ~/Projects/personal/fusion/add-ins/AutodeskFusionMCP show compute-all -- fusion_bridge tests README.md`)
1. A module in `fusion_bridge/<name>.py` with a handler `def <tool>(arguments) -> dict` returning MCP content
   (`{"content": [{"type": "text", "text": ...}]}`, `"isError": True` on failure). Validate arguments first and
   return clear errors without touching Fusion.
2. Tool constant + definition (name, description, strict `inputSchema` with `additionalProperties: False`)
   in `fusion_bridge/tool_surface.py`, and the handler in `build_tool_handlers` (the registry must match).
3. Register the handler in `fusion_bridge/operations.py` with `_wrap(...)`.
4. A row in the README tool table.
5. Tests in `tests/` (the `_fusion_test_bootstrap` mocks `adsk`). Cover schema, argument validation, and the
   pure logic (factor Fusion-free logic into small functions so it is testable with fakes). Add the tool name to
   the expected set in `tests/test_tool_contract.py`.
6. Run `python3 -m unittest discover -s tests` from the worktree root (CI command). All must pass.

Read the Fusion API docs when unsure of a member: the local stubs/docs in the repo, or reason from
`adsk.core` / `adsk.fusion` names you know; flag anything you could not verify.

## Report back (keep it short)
- Branch, commit hash(es), files changed, test count result.
- The tool's interface (args + result shape).
- **Live checks needed**: exact steps the lead should run in real Fusion to verify, and any API member you
  were not sure exists or behaves as assumed.

## Known Fusion gotchas (useful context)
- API edits are rolled back while the timeline has broken features; Fusion raises a long dump listing every
  broken feature.
- Reads from a non-active document return partial data; only the active document is reliable.
- Personal Use licence: most documents open read-only (`DataFile.isReadOnly`), saves silently do nothing;
  the API cannot change the flag.
- Closing a document also closes documents it links, invalidating held `Document` objects.
- Fusion runs API calls on its main thread; the bridge dispatches to it (see `dispatch.py`). A modal dialog
  blocks the main thread ("Request cancelled").

## Update 2026-11-05
- The main checkout is on branch `combined` and is the live add-in; never touch it. Your branch comes off `main`, so features from other branches (`document_io`, `documents`, `data_tree`, `app_log`, `DIRECT_TOOL_NAMES`) are not there unless your task says otherwise. Keep your code self-contained; duplicate a small helper rather than depend on another branch. Read other branches with `git show <branch>:<path>` when useful.
- The schema-keyword test rejects `minItems`, `minLength`, `uniqueItems`, `anyOf`, `oneOf`: validate in the handler.
- Live facts: read `LIVE-ISSUES.md` next to this file before designing. Fusion vectors (e.g. `DataFileVector`) iterate but have no `count`/`item`.

## Update for primitives (2026-11-05, replaces the "self-contained" advice above)
Primitive branches come off `combined`, NOT `main`. Use `fusion_bridge/common/` for everything shared (README "Shared code"); never add a private copy of a helper. Import in tests as `from fusion_bridge.common import x`, not by full submodule path. Specs: `PRIMITIVES.md` next to this file; its Gate 0 results and Decisions sections at the end override anything earlier. Build tools default to `dry_run: false`; helper geometry is named and listed, light bulb off.
