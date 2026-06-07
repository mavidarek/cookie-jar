#!/bin/bash
set -e

echo ""
echo "=== Oatmeal Installer ==="
echo ""

# --- Check macOS ---
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: Oatmeal only works on macOS."
    exit 1
fi

# --- Check Python 3 ---
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is required. Install it from python.org or via: brew install python"
    exit 1
fi

INSTALL_DIR="$HOME/.oatmeal"
VENV_DIR="$INSTALL_DIR/venv"
APP_DIR="$HOME/Applications/Oatmeal.app"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.oatmeal.plist"
LOG_DIR="$HOME/logs"
SCRIPT_SRC="$(cd "$(dirname "$0")" && pwd)/oatmeal.py"
ICON_SRC="$(cd "$(dirname "$0")" && pwd)/icon.png"

echo "Installing to: $INSTALL_DIR"
echo ""

# --- Create install directory ---
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_SRC" "$INSTALL_DIR/oatmeal.py"
chmod +x "$INSTALL_DIR/oatmeal.py"

# --- Create virtual environment ---
echo "Setting up Python environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet httpx
echo "  Done"

# --- Create the .app bundle ---
echo "Creating Oatmeal app..."
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/MacOS/oatmeal" << WRAPPER
#!/bin/bash
"$VENV_DIR/bin/python3" "$INSTALL_DIR/oatmeal.py" --manual
sleep 5
WRAPPER
chmod +x "$APP_DIR/Contents/MacOS/oatmeal"

cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>oatmeal</string>
    <key>CFBundleName</key>
    <string>Oatmeal</string>
    <key>CFBundleIdentifier</key>
    <string>com.oatmeal.app</string>
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
    ICONSET="/tmp/Oatmeal.iconset"
    rm -rf "$ICONSET"
    mkdir -p "$ICONSET"
    sips -s format png "$ICON_SRC" --out /tmp/oatmeal-base.png > /dev/null 2>&1
    for sz in 16 32 64 128 256 512 1024; do
        sips -z $sz $sz /tmp/oatmeal-base.png --out "$ICONSET/icon_${sz}x${sz}.png" > /dev/null 2>&1
    done
    cp "$ICONSET/icon_32x32.png" "$ICONSET/icon_16x16@2x.png"
    cp "$ICONSET/icon_64x64.png" "$ICONSET/icon_32x32@2x.png"
    cp "$ICONSET/icon_256x256.png" "$ICONSET/icon_128x128@2x.png"
    cp "$ICONSET/icon_512x512.png" "$ICONSET/icon_256x256@2x.png"
    cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"
    rm -f "$ICONSET/icon_64x64.png" "$ICONSET/icon_1024x1024.png"
    iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/AppIcon.icns" 2>/dev/null
    rm -rf "$ICONSET" /tmp/oatmeal-base.png
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
    <string>com.oatmeal</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_DIR/bin/python3</string>
        <string>$INSTALL_DIR/oatmeal.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/oatmeal.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/oatmeal.log</string>
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
"$VENV_DIR/bin/python3" "$INSTALL_DIR/oatmeal.py" --manual

echo ""
echo "=== Installation complete ==="
echo ""
echo "  Oatmeal is now syncing your Granola notes every hour."
echo "  Find 'Oatmeal' in Spotlight or ~/Applications to run manually."
echo "  Your meeting notes sync to: ~/Oatmeal/"
echo ""
echo "  Tip: Drag the Oatmeal app to your Dock for one-click access."
echo ""
