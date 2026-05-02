#!/bin/bash
set -e

INSTALL_PATH="/usr/local/bin/overcast-upload"
WORKFLOW_SRC="Upload to Overcast.workflow"
WORKFLOW_DEST="$HOME/Library/Services/Upload to Overcast.workflow"

echo "=== overcast-upload installer ==="
echo

# Install CLI
echo "Installing overcast-upload to $INSTALL_PATH..."
sudo mkdir -p /usr/local/bin
sudo cp overcast-upload "$INSTALL_PATH"
sudo chmod +x "$INSTALL_PATH"
echo "Done."
echo

# Install Python dependency
echo "Installing Python dependency (requests)..."
pip3 install --quiet requests
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
