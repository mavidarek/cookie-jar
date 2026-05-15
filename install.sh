#!/bin/bash
set -e

echo ""
echo "=== Cookie Jar Installer ==="
echo ""

# --- Check macOS ---
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: Cookie Jar only works on macOS."
    exit 1
fi

# --- Check Python 3 ---
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is required. Install it from python.org or via: brew install python"
    exit 1
fi

INSTALL_DIR="$HOME/.cookie-jar"
VENV_DIR="$INSTALL_DIR/venv"
APP_DIR="$HOME/Applications/Cookie Jar.app"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.cookie-jar.plist"
LOG_DIR="$HOME/logs"
SCRIPT_SRC="$(cd "$(dirname "$0")" && pwd)/cookie-jar.py"
ICON_SRC="$(cd "$(dirname "$0")" && pwd)/icon.png"

echo "Installing to: $INSTALL_DIR"
echo ""

# --- Create install directory ---
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_SRC" "$INSTALL_DIR/cookie-jar.py"
chmod +x "$INSTALL_DIR/cookie-jar.py"

# --- Create virtual environment ---
echo "Setting up Python environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet httpx
echo "  Done"

# --- Create the .app bundle ---
echo "Creating Cookie Jar app..."
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/MacOS/cookie-jar" << WRAPPER
#!/bin/bash
"$VENV_DIR/bin/python3" "$INSTALL_DIR/cookie-jar.py" --manual
sleep 5
WRAPPER
chmod +x "$APP_DIR/Contents/MacOS/cookie-jar"

cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>cookie-jar</string>
    <key>CFBundleName</key>
    <string>Cookie Jar</string>
    <key>CFBundleIdentifier</key>
    <string>com.cookie-jar.app</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# --- Convert icon to .icns ---
if [[ -f "$ICON_SRC" ]]; then
    ICONSET="/tmp/CookieJar.iconset"
    rm -rf "$ICONSET"
    mkdir -p "$ICONSET"
    sips -s format png "$ICON_SRC" --out /tmp/cookiejar-base.png > /dev/null 2>&1
    for sz in 16 32 64 128 256 512 1024; do
        sips -z $sz $sz /tmp/cookiejar-base.png --out "$ICONSET/icon_${sz}x${sz}.png" > /dev/null 2>&1
    done
    cp "$ICONSET/icon_32x32.png" "$ICONSET/icon_16x16@2x.png"
    cp "$ICONSET/icon_64x64.png" "$ICONSET/icon_32x32@2x.png"
    cp "$ICONSET/icon_256x256.png" "$ICONSET/icon_128x128@2x.png"
    cp "$ICONSET/icon_512x512.png" "$ICONSET/icon_256x256@2x.png"
    cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"
    rm -f "$ICONSET/icon_64x64.png" "$ICONSET/icon_1024x1024.png"
    iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/AppIcon.icns" 2>/dev/null
    rm -rf "$ICONSET" /tmp/cookiejar-base.png
    echo "  App icon set"
fi

# --- Install LaunchAgent (every hour on the hour) ---
echo "Setting up automatic sync (every hour)..."
mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$LAUNCH_AGENT")"

cat > "$LAUNCH_AGENT" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cookie-jar</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_DIR/bin/python3</string>
        <string>$INSTALL_DIR/cookie-jar.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/cookie-jar.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/cookie-jar.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$VENV_DIR/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
PLIST

launchctl bootout gui/$(id -u) "$LAUNCH_AGENT" 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$LAUNCH_AGENT"
echo "  Done"

# --- Register the app ---
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DIR" 2>/dev/null

# --- Run first sync (triggers API key prompt) ---
echo ""
echo "Running first sync — a dialog will ask for your Granola API key."
echo "Find it at: granola.ai > Settings > API"
echo ""
"$VENV_DIR/bin/python3" "$INSTALL_DIR/cookie-jar.py" --manual

echo ""
echo "=== Installation complete ==="
echo ""
echo "  Cookie Jar is now syncing your Granola notes every hour."
echo "  Find 'Cookie Jar' in Spotlight or ~/Applications to run manually."
echo "  Your meeting notes sync to: ~/Documents/Cookie Jar/"
echo ""
echo "  Tip: Drag the Cookie Jar app to your Dock for one-click access."
echo ""
