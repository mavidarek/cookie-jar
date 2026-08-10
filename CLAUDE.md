# CLAUDE.md — oatmeal

Granola → local-files sync (single script, `oatmeal.py`; installed as a launchd
LaunchAgent by `install.sh`). Notes land in `~/Oatmeal/`. A second, separate
stage at `~/mycelium/scripts/oatmeal/` distills those notes into briefs in
`~/CookieJar/` — that stage is mycelium's, not this repo's.

## Load-bearing constraints (violating these breaks a running pipeline)

- **The `com.oatmeal` LaunchAgent is LOAD-BEARING, not legacy.** The mycelium
  distiller runs 15 minutes after it and depends on its output. It was nearly
  retired 2026-07-09 on a wrong "legacy duplicate" diagnosis. Never disable or
  retire it while the mycelium oatmeal pipeline exists.
- **Never move the notes directory under `~/Documents`.** macOS TCC blocks
  launchd background agents from reading `~/Documents` — the hourly sync fails
  silently with PermissionError while interactive runs work, which is exactly
  how it broke before. Full Disk Access on the venv python does NOT fix it (the
  venv python is a symlink to the system CLT python). `~/Oatmeal` needs no TCC
  grant; keep it there.
- **Never wire Granola ingestion into Magi** (mars). The old mars pipeline was
  deliberately decommissioned 2026-06-07 for the Chico firewall. If an agent
  should ever ingest meeting notes, the right home is Vayu.

Sensitive-content routing rules (what may leave the MacBook) live in the
mycelium context, not here — read `~/mycelium/CONTEXT.md` before changing where
any output syncs.
