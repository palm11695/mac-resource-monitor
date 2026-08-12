#!/bin/bash
# Remove the resmon LaunchAgents. Data in logs/ is kept.
# Set RESMON_LABEL if you installed with a custom label prefix.
set -uo pipefail

LABEL="${RESMON_LABEL:-local.resmon}"
UID_N="$(id -u)"

for l in "$LABEL" "$LABEL.web"; do
  launchctl bootout "gui/$UID_N/$l" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$l.plist"
done
echo "uninstalled $LABEL + $LABEL.web (logs/ kept)"
