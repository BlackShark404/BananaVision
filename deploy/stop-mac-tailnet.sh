#!/bin/bash
# Stop the stack started by deploy/start-mac-tailnet.sh.
set -euo pipefail

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/bananavision-tailnet"
BACKEND_PID_FILE="$STATE_DIR/backend.pid"
CADDY_PID_FILE="$STATE_DIR/caddy.pid"

stop_pid_file() {
	local file="$1"
	local expected="$2"
	[[ -f "$file" ]] || return 0
	local pid command
	pid="$(cat "$file" 2>/dev/null || true)"
	if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
		command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
		if [[ "$command" == *"$expected"* ]]; then
			kill "$pid" 2>/dev/null || true
			for _ in {1..20}; do
				kill -0 "$pid" 2>/dev/null || break
				sleep 0.25
			done
			if kill -0 "$pid" 2>/dev/null; then
				kill -9 "$pid" 2>/dev/null || true
			fi
			echo "stopped: $expected"
		else
			echo "warning: pid $pid does not look like '$expected'; not killing it" >&2
		fi
	fi
	rm -f "$file"
}

if command -v tailscale >/dev/null && tailscale serve status 2>/dev/null | grep -qF 'proxy http://127.0.0.1:8080'; then
	tailscale serve --https=443 off
	echo "stopped: Tailscale Serve"
else
	echo "Tailscale Serve was not exposing this proxy"
fi

stop_pid_file "$CADDY_PID_FILE" "caddy run"
stop_pid_file "$BACKEND_PID_FILE" "uvicorn app.main:app"

echo "BananaVision tailnet stack stopped"
