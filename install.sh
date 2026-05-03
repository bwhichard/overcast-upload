#!/bin/bash
set -e

WORKFLOW_SRC="Upload to Overcast.workflow"
WORKFLOW_DEST="$HOME/Library/Services/Upload to Overcast.workflow"

echo "=== overcast-upload installer ==="
echo

# Install CLI
echo "Installing overcast-upload..."
if command -v uv &>/dev/null; then
    uv tool install .
elif command -v pipx &>/dev/null; then
    echo "Note: uv not found — install it for a cleaner setup: brew install uv"
    pipx install .
else
    echo "Error: Install uv first: brew install uv"
    exit 1
fi
echo "Done."
echo

# Install Finder Quick Action
if [ -d "$WORKFLOW_SRC" ]; then
    echo "Installing Finder Quick Action..."
    cp -r "$WORKFLOW_SRC" "$WORKFLOW_DEST"
    /System/Library/CoreServices/pbs -update
    echo "Done. Restart Finder for the Quick Action to appear."
    echo "  killall Finder"
    echo
fi

echo "=== Installation complete ==="
echo
echo "Run setup to save your Overcast credentials:"
echo "  overcast-upload --setup"
