#!/bin/bash
# Install the resmon LaunchAgents (sampler + dashboard) for the current user.
# Plists are generated here with this machine's paths — nothing is hardcoded
# in the repo. Configuration via environment variables:
#
#   RESMON_LABEL      launchd label prefix   (default: local.resmon)
#   RESMON_PYTHON     python3 to use         (default: first python3 on PATH)
#   RESMON_INTERVAL   sample every N seconds (default: 10)
#   RESMON_HOST       dashboard bind address (default: 127.0.0.1)
#   RESMON_PORT       dashboard port         (default: 8737)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="${RESMON_LABEL:-local.resmon}"
PYTHON="${RESMON_PYTHON:-$(command -v python3 || true)}"
INTERVAL="${RESMON_INTERVAL:-10}"
HOST="${RESMON_HOST:-127.0.0.1}"
PORT="${RESMON_PORT:-8737}"
AGENTS_DIR="$HOME/Library/LaunchAgents"
UID_N="$(id -u)"

[ -n "$PYTHON" ] && [ -x "$PYTHON" ] || {
  echo "python3 not found — set RESMON_PYTHON to a python3 path" >&2
  exit 1
}
mkdir -p "$AGENTS_DIR" "$DIR/logs"

write_plist() {
  local label="$1" script="$2" envs="$3" logname="$4"
  cat > "$AGENTS_DIR/$label.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>$label</string>
	<key>ProgramArguments</key>
	<array>
		<string>$PYTHON</string>
		<string>$DIR/$script</string>
	</array>
	<key>EnvironmentVariables</key>
	<dict>
$envs
	</dict>
	<key>KeepAlive</key><true/>
	<key>RunAtLoad</key><true/>
	<key>StandardOutPath</key><string>$DIR/logs/$logname.out.log</string>
	<key>StandardErrorPath</key><string>$DIR/logs/$logname.err.log</string>
	<key>ProcessType</key><string>Background</string>
	<key>Nice</key><integer>10</integer>
</dict>
</plist>
EOF
}

write_plist "$LABEL" sampler.py \
"		<key>RESMON_INTERVAL</key><string>$INTERVAL</string>" sampler
write_plist "$LABEL.web" server.py \
"		<key>RESMON_HOST</key><string>$HOST</string>
		<key>RESMON_PORT</key><string>$PORT</string>" web

for l in "$LABEL" "$LABEL.web"; do
  launchctl bootout "gui/$UID_N/$l" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_N" "$AGENTS_DIR/$l.plist"
done

echo "installed:"
echo "  sampler   $LABEL      (every ${INTERVAL}s)"
echo "  dashboard $LABEL.web  http://$HOST:$PORT"
