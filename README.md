# Cookie Jar

Automatically sync your [Granola](https://granola.ai) meeting notes, transcripts, and summaries to your Mac as local files.

**macOS only.** Requires Python 3.9+.

## What it does

- Syncs all your Granola meeting notes to `~/Documents/Cookie Jar/` as Markdown and JSON files
- Runs automatically every 15 minutes in the background
- Installs a one-click app you can pin to your Dock for manual syncs
- Stores your API key securely in macOS Keychain (not a plaintext file)
- Sends a macOS notification when new notes are synced

## Install

1. Get your Granola API key from [granola.ai](https://granola.ai) > Settings > API
2. Open Terminal and run:

```bash
git clone https://github.com/mavidarek/cookie-jar.git
cd cookie-jar
./install.sh
```

3. Paste your API key when the dialog pops up

That's it. Your notes will start syncing immediately.

## Using with Claude Code

Add this to your `CLAUDE.md` to give Claude access to your meeting notes:

```
Meeting transcripts from Granola sync to ~/Documents/Cookie Jar/ as .md and .json files via the Cookie Jar app.
Each file is named YYYY-MM-DD_Meeting-Title.md and contains the date, participants, AI summary, and full transcript.
Search them by date, participant name, or topic when I reference a meeting.
```

## What gets installed

| What | Where |
|------|-------|
| Sync script | `~/.cookie-jar/cookie-jar.py` |
| Python venv | `~/.cookie-jar/venv/` |
| App | `~/Applications/Cookie Jar.app` |
| Background job | `~/Library/LaunchAgents/com.cookie-jar.plist` |
| Synced notes | `~/Documents/Cookie Jar/` |
| Logs | `~/logs/cookie-jar.log` |
| API key | macOS Keychain (service: `cookie-jar`) |

## Uninstall

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cookie-jar.plist
rm -rf ~/.cookie-jar
rm -rf ~/Applications/Cookie\ Jar.app
rm ~/Library/LaunchAgents/com.cookie-jar.plist
security delete-generic-password -s cookie-jar -a api-key
```

Your synced notes in `~/Documents/Cookie Jar/` are not deleted.

## Security

- Your API key is stored in macOS Keychain (encrypted), never in a plaintext file
- The script only connects to `public-api.granola.ai` — no other network calls
- No sudo or admin privileges required
- Fully open source — read the code before you run it
