#!/usr/bin/env python3
"""
Cookie Jar — Granola transcript sync via the official REST API.
Fetches all meeting notes, summaries, and transcripts to local files.

No LLM, no MCP, no OAuth. Just httpx + API key.
Evergreen: safe to re-run, self-healing.
"""
import json
import sys
import time
from pathlib import Path

import re

import subprocess

import httpx

# --- Config ---
API_BASE = "https://public-api.granola.ai/v1"
GRANOLA_DIR = Path.home() / "Documents" / "Cookie Jar"
ENV_FILE = Path.home() / ".config" / "granola-sync" / ".env"  # legacy, migrated to Keychain
ID_MAP_FILE = GRANOLA_DIR / "id_map.json"
KEYCHAIN_SERVICE = "cookie-jar"
KEYCHAIN_ACCOUNT = "api-key"
LOOKBACK_DATE = "2026-01-01T00:00:00Z"  # fetch everything from this date forward
BASE_DELAY = 1.0  # seconds between requests (well under 5/sec limit)
MAX_RETRIES = 3

# Error strings that indicate a corrupted transcript (only match whole-message errors)
CORRUPTION_MARKERS = [
    "rate limit exceeded",
    "too many requests",
    "503 service unavailable",
    "502 bad gateway",
    "unauthorized",
    "internal server error",
]


def notify(title: str, message: str):
    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}"',
    ])


def slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    s = re.sub(r'[^\w\s-]', '', title).strip()
    s = re.sub(r'[\s]+', '-', s)
    return s[:60]


def make_filename(not_id: str, title: str, created_at: str, id_map: dict) -> str:
    """Generate a date_title filename, handling collisions."""
    date = created_at[:10] if created_at else "undated"
    slug = slugify(title or "Untitled")
    base = f"{date}_{slug}"

    # Check if this name already exists for a different not_id
    existing_names = set(id_map.values())
    if base not in existing_names:
        return base

    # Add sequence number for collision
    for i in range(2, 100):
        candidate = f"{base}_{i}"
        if candidate not in existing_names:
            return candidate
    return f"{base}_{not_id}"  # fallback


def keychain_get() -> str | None:
    r = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def keychain_set(api_key: str):
    subprocess.run(
        ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT],
        capture_output=True,
    )
    subprocess.run(
        ["security", "add-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w", api_key],
        check=True,
    )


def prompt_for_api_key() -> str | None:
    script = '''
    tell application "System Events"
        display dialog "Paste your Granola API key:" & return & return & "Find it at: granola.ai → Settings → API" with title "Cookie Jar Setup" default answer "" with hidden answer
        set theKey to text returned of result
        if theKey is "" then return ""
        return theKey
    end tell
    '''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    key = r.stdout.strip()
    return key if key else None


def load_api_key() -> str:
    key = keychain_get()
    if key:
        return key

    # Migrate from legacy .env file
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().strip().splitlines():
            if line.startswith("GRANOLA_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    print("  Migrating API key from .env to Keychain...")
                    keychain_set(key)
                    return key

    # First run — prompt the user
    key = prompt_for_api_key()
    if not key:
        notify("Cookie Jar", "Setup cancelled — no API key provided")
        sys.exit(1)

    keychain_set(key)
    notify("Cookie Jar", "API key saved to Keychain ✓")
    return key


def load_id_map() -> dict:
    """Load the not_ID <-> UUID mapping."""
    if ID_MAP_FILE.exists():
        return json.loads(ID_MAP_FILE.read_text())
    return {}


def save_id_map(id_map: dict):
    ID_MAP_FILE.write_text(json.dumps(id_map, indent=2), encoding="utf-8")


def is_corrupted(transcript_value) -> bool:
    """Check if a transcript field contains error text instead of real content."""
    if not transcript_value:
        return False
    # Structured transcripts (list of dicts) from the REST API are never corrupted
    if isinstance(transcript_value, list):
        return False
    # Only string transcripts (from old MCP runs) can be corrupted
    text = str(transcript_value).lower().strip()
    for marker in CORRUPTION_MARKERS:
        if marker in text:
            return True
    return False


def format_transcript_text(transcript_data: list) -> str:
    """Convert structured transcript JSON to readable plain text."""
    if not transcript_data:
        return ""
    lines = []
    for entry in transcript_data:
        speaker = entry.get("speaker", {})
        source = speaker.get("name") or speaker.get("source", "Unknown")
        text = entry.get("text", "")
        if text:
            lines.append(f"{source}: {text}")
    return "\n".join(lines)


def write_note_files(note_id: str, note_data: dict):
    """Write/update the .json and .md files for a note."""
    json_path = GRANOLA_DIR / f"{note_id}.json"
    md_path = GRANOLA_DIR / f"{note_id}.md"

    # Write JSON (full API response)
    json_path.write_text(json.dumps(note_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write MD (human-readable)
    title = note_data.get("title", "Untitled")
    created = note_data.get("created_at", "")
    attendees = note_data.get("attendees", [])
    attendee_names = ", ".join(a.get("name", a.get("email", "")) for a in attendees)
    summary = note_data.get("summary_markdown") or note_data.get("summary_text") or ""
    transcript = note_data.get("transcript", [])
    transcript_text = format_transcript_text(transcript) if isinstance(transcript, list) else str(transcript)

    md_parts = [
        f"# {title}",
        "",
        f"**Date:** {created}",
        f"**Participants:** {attendee_names}",
    ]

    if summary:
        md_parts += ["", "## Summary", "", summary]

    md_parts += ["", "## Transcript", "", transcript_text if transcript_text else "(no transcript)"]

    md_path.write_text("\n".join(md_parts), encoding="utf-8")


def cleanup_corrupted(stats: dict):
    """Phase 0: Find and reset corrupted transcript files."""
    for f in GRANOLA_DIR.glob("*.json"):
        if f.name in ("id_map.json", "index.json"):
            continue
        try:
            data = json.loads(f.read_text())
            transcript = data.get("transcript")
            if transcript and is_corrupted(transcript):
                print(f"  Fixing corrupted: {f.stem[:12]}... ({data.get('title', '')[:40]})")
                data["transcript"] = ""
                f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                stats["corrupted_fixed"] += 1
        except Exception:
            pass


def api_get(client: httpx.Client, path: str, params: dict | None = None) -> httpx.Response:
    """Make an API request with retry + exponential backoff on 429."""
    delay = BASE_DELAY
    for attempt in range(MAX_RETRIES + 1):
        r = client.get(f"{API_BASE}{path}", params=params)
        if r.status_code == 200:
            return r
        if r.status_code == 429:
            delay = min(delay * 2, 16)
            print(f"  429 rate limited, backing off {delay:.0f}s (attempt {attempt + 1}/{MAX_RETRIES + 1})")
            time.sleep(delay)
            continue
        if r.status_code == 404:
            return r  # note might not have AI summary yet
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        return r
    return r  # return last response after all retries


def sync():
    GRANOLA_DIR.mkdir(parents=True, exist_ok=True)
    api_key = load_api_key()
    id_map = load_id_map()

    stats = {
        "corrupted_fixed": 0,
        "new_notes": 0,
        "transcripts_fetched": 0,
        "skipped": 0,
        "errors": 0,
    }

    # Phase 0: Cleanup corrupted files
    print("=== Phase 0: Cleaning up corrupted files ===")
    cleanup_corrupted(stats)
    if stats["corrupted_fixed"]:
        print(f"  Fixed {stats['corrupted_fixed']} corrupted files")
    else:
        print("  None found")

    # Phase 1: List all notes from API
    print("\n=== Phase 1: Listing all notes from Granola ===")
    client = httpx.Client(
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )

    all_notes = []
    cursor = None
    page = 0

    while True:
        page += 1
        params = {"created_after": LOOKBACK_DATE}
        if cursor:
            params["cursor"] = cursor

        r = api_get(client, "/notes", params=params)
        if r.status_code != 200:
            print(f"  ERROR listing notes: HTTP {r.status_code}")
            break

        data = r.json()
        notes = data.get("notes", [])
        all_notes.extend(notes)
        print(f"  Page {page}: {len(notes)} notes (total: {len(all_notes)})")

        if not data.get("hasMore"):
            break
        cursor = data.get("cursor")
        time.sleep(BASE_DELAY)

    print(f"  Total notes from API: {len(all_notes)}")

    # Build/update ID map and create stubs for new notes
    existing_not_ids = set(id_map.keys())
    existing_files = {f.stem for f in GRANOLA_DIR.glob("*.json") if f.name not in ("id_map.json", "index.json")}

    for note in all_notes:
        not_id = note["id"]
        if not_id not in id_map:
            filename = make_filename(
                not_id,
                note.get("title", "Untitled"),
                note.get("created_at", ""),
                id_map,
            )
            id_map[not_id] = filename
        filename = id_map[not_id]

        if filename not in existing_files:
            # Create stub
            write_note_files(filename, {
                "id": not_id,
                "title": note.get("title", "Untitled"),
                "created_at": note.get("created_at", ""),
                "updated_at": note.get("updated_at", ""),
                "owner": note.get("owner", {}),
                "attendees": note.get("attendees", []),
                "transcript": "",
                "summary_text": "",
            })
            stats["new_notes"] += 1
            existing_files.add(filename)

    save_id_map(id_map)
    if stats["new_notes"]:
        print(f"  Created {stats['new_notes']} new note stubs")

    # Phase 2: Fetch full notes + transcripts for those that need it
    print("\n=== Phase 2: Fetching transcripts ===")

    # Find notes that need transcripts (empty, corrupted, or missing summary)
    needs_fetch = []
    for note in all_notes:
        not_id = note["id"]
        filename = id_map.get(not_id, not_id)
        json_path = GRANOLA_DIR / f"{filename}.json"

        if not json_path.exists():
            needs_fetch.append((not_id, filename, note.get("title", "")))
            continue

        try:
            existing = json.loads(json_path.read_text())
            transcript = existing.get("transcript")
            summary = existing.get("summary_text") or existing.get("summary_markdown")

            # Re-fetch if: corrupted transcript, or no summary (never successfully fetched)
            if is_corrupted(transcript) or not summary:
                needs_fetch.append((not_id, filename, note.get("title", "")))
        except Exception:
            needs_fetch.append((not_id, filename, note.get("title", "")))

    if not needs_fetch:
        print("  All notes fully synced!")
    else:
        print(f"  Notes needing fetch: {len(needs_fetch)}")

        for i, (not_id, filename, title) in enumerate(needs_fetch):
            print(f"\n  [{i + 1}/{len(needs_fetch)}] {title[:60]}")

            r = api_get(client, f"/notes/{not_id}", params={"include": "transcript"})

            if r.status_code == 404:
                print(f"    Skipped (no AI summary yet)")
                stats["skipped"] += 1
                continue

            if r.status_code != 200:
                print(f"    ERROR: HTTP {r.status_code}")
                stats["errors"] += 1
                continue

            note_data = r.json()

            # Validate transcript before writing
            transcript = note_data.get("transcript")
            if transcript and is_corrupted(transcript):
                print(f"    Skipped (response looks like error)")
                stats["errors"] += 1
                continue

            write_note_files(filename, note_data)
            t_len = len(json.dumps(transcript)) if transcript else 0
            print(f"    OK ({t_len} chars transcript, has summary: {bool(note_data.get('summary_text'))})")
            stats["transcripts_fetched"] += 1

            time.sleep(BASE_DELAY)

    client.close()

    # Summary
    print("\n=== Summary ===")
    print(f"  Corrupted fixed:    {stats['corrupted_fixed']}")
    print(f"  New notes created:  {stats['new_notes']}")
    print(f"  Transcripts fetched:{stats['transcripts_fetched']}")
    print(f"  Skipped (no AI):    {stats['skipped']}")
    print(f"  Errors:             {stats['errors']}")

    # Count final state
    total = 0
    with_transcript = 0
    for f in GRANOLA_DIR.glob("*.json"):
        if f.name in ("id_map.json", "index.json"):
            continue
        total += 1
        try:
            d = json.loads(f.read_text())
            if d.get("transcript") and not is_corrupted(d["transcript"]):
                with_transcript += 1
        except Exception:
            pass
    print(f"\n  Total notes on disk: {total}")
    print(f"  With transcript:     {with_transcript}")
    print(f"  Remaining:           {total - with_transcript}")

    manual = "--manual" in sys.argv
    has_changes = stats["new_notes"] or stats["transcripts_fetched"]

    if has_changes:
        parts = []
        if stats["new_notes"]:
            parts.append(f"{stats['new_notes']} new")
        if stats["transcripts_fetched"]:
            parts.append(f"{stats['transcripts_fetched']} transcripts")
        notify("Cookie Jar", f"Synced {', '.join(parts)} ({total} total)")
    elif stats["errors"]:
        notify("Cookie Jar", f"{stats['errors']} error(s) — check logs")
    elif manual:
        notify("Cookie Jar", f"All {total} notes up to date")

    # Open Finder with newest file selected on manual runs
    if manual:
        md_files = sorted(GRANOLA_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if md_files:
            subprocess.run(["open", "-R", str(md_files[0])])
        else:
            subprocess.run(["open", str(GRANOLA_DIR)])


if __name__ == "__main__":
    sync()
