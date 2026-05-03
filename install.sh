#!/bin/bash
set -e

WORKFLOW_SRC="Upload to Overcast.workflow"
WORKFLOW_DEST="$HOME/Library/Services/Upload to Overcast.workflow"

echo "=== overcast-upload installer ==="
echo

# Install CLI
echo "Installing overcast-upload..."
if command -v pipx &>/dev/null; then
    pipx install .
elif command -v pip3 &>/dev/null; then
    echo "Note: pipx not found — install it for a cleaner setup: brew install pipx && pipx ensurepath"
    echo "Falling back to: pip3 install --user ."
    pip3 install --user .
else
    echo "Error: Python 3 not found. Install it and try again."
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
