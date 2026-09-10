# Notion read/custody gate

Status: **NOTION_TARGET_MISSING**.

SCOPE_UPDATE.md: only a database/page the user names by link or ID may be read. No workspace scan, no THBISON IDs guessed from history, no writes.

This Grok task did not designate a target. M4 therefore keeps `custody=NOTION_TARGET_MISSING` and continues on synthetic fixtures.

To complete the gate later, inject `NOTION_TARGET_ID` (or a page URL) into a private run, store the snapshot under `private/` (gitignored, not in the source ZIP), and set `NOTION_READ_VERIFIED=1` only after a consistent hash receipt. Never attach raw Notion payloads to a public GitHub Release.
