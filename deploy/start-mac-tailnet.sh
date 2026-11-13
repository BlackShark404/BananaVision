#!/bin/bash
# Start BananaVision on this Mac and expose it over Tailscale Serve HTTPS.
# The backend and Caddy listen on loopback only; Tailscale forwards tailnet traffic.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
CADDYFILE="$ROOT_DIR/deploy/Caddyfile"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/bananavision-tailnet"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/bananavision"
CADDY_VERSION="${CADDY_VERSION:-2.11.9}"
CADDY_BIN="${CADDY_BIN:-$CACHE_DIR/caddy-$CADDY_VERSION/caddy}"
BACKEND_PID_FILE="$STATE_DIR/backend.pid"
CADDY_PID_FILE="$STATE_DIR/caddy.pid"
BACKEND_LOG="$STATE_DIR/backend.log"
CADDY_LOG="$STATE_DIR/caddy.log"

SKIP_BUILD=0
if [[ "${1:-}" == "--skip-build" ]]; then
	SKIP_BUILD=1
elif [[ $# -gt 0 ]]; then
	echo "usage: $0 [--skip-build]" >&2
	exit 2
fi

fail() {
	echo "error: $*" >&2
	exit 1
}

STARTED_BACKEND=0
STARTED_CADDY=0
STARTED_SERVE=0

stop_pid_file() {
	local file="$1"
	[[ -f "$file" ]] || return 0
	local pid
	pid="$(cat "$file" 2>/dev/null || true)"
	if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
		kill "$pid" 2>/dev/null || true
	fi
	rm -f "$file"
}

cleanup_on_error() {
	local status=$?
	trap - EXIT
	if [[ $status -ne 0 ]]; then
		echo "start failed; cleaning up" >&2
		if [[ $STARTED_SERVE -eq 1 ]]; then
			tailscale serve --https=443 off >/dev/null 2>&1 || true
		fi
		if [[ $STARTED_CADDY -eq 1 ]]; then
			stop_pid_file "$CADDY_PID_FILE"
		fi
		if [[ $STARTED_BACKEND -eq 1 ]]; then
			stop_pid_file "$BACKEND_PID_FILE"
		fi
		if [[ $STARTED_BACKEND -eq 1 || $STARTED_CADDY -eq 1 ]]; then
			echo "logs: $BACKEND_LOG $CADDY_LOG" >&2
		fi
	fi
	exit "$status"
}
trap cleanup_on_error EXIT

[[ "$(uname -s)" == "Darwin" ]] || fail "this script targets macOS"
case "$(uname -m)" in
	arm64) CADDY_ARCH="arm64" ;;
	x86_64) CADDY_ARCH="amd64" ;;
	*) fail "unsupported architecture: $(uname -m)" ;;
esac

command -v curl >/dev/null || fail "curl is required"
command -v npm >/dev/null || fail "npm is required"
command -v python3 >/dev/null || fail "python3 is required"
command -v tailscale >/dev/null || fail "Tailscale is required"
[[ -x "$BACKEND_DIR/venv/bin/python" ]] || fail "backend venv missing: $BACKEND_DIR/venv"
[[ -d "$FRONTEND_DIR/node_modules" ]] || fail "frontend dependencies missing; run npm install in $FRONTEND_DIR"
[[ -f "$CADDYFILE" ]] || fail "missing $CADDYFILE"

tailscale status >/dev/null 2>&1 || fail "Tailscale is not connected"

DNS_NAME="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
[[ -n "$DNS_NAME" ]] || fail "could not read the tailnet DNS name"
PUBLIC_URL="https://$DNS_NAME"

port_busy() {
	lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

for pid_file in "$BACKEND_PID_FILE" "$CADDY_PID_FILE"; do
	if [[ -f "$pid_file" ]]; then
		pid="$(cat "$pid_file" 2>/dev/null || true)"
		if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
			fail "BananaVision is already running; run deploy/stop-mac-tailnet.sh first"
		fi
		rm -f "$pid_file"
	fi
done

port_busy 8000 && fail "port 8000 is already in use"
port_busy 8080 && fail "port 8080 is already in use"

if tailscale serve status 2>/dev/null | grep -q '|--'; then
	fail "Tailscale Serve already has a configuration; run 'tailscale serve status' and clear it first"
fi

mkdir -p "$STATE_DIR/caddy/data" "$STATE_DIR/caddy/config" "$(dirname "$CADDY_BIN")"

if [[ ! -x "$CADDY_BIN" ]]; then
	archive_name="caddy_${CADDY_VERSION}_mac_${CADDY_ARCH}.tar.gz"
	archive="$CACHE_DIR/$archive_name"
	echo "downloading Caddy $CADDY_VERSION..."
	curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v$CADDY_VERSION/$archive_name" -o "$archive"
	# Caddy's checksums.txt disagrees with its published 2.11.9 assets; the per-asset digest is authoritative.
	expected="$(curl -fsSL "https://api.github.com/repos/caddyserver/caddy/releases/tags/v$CADDY_VERSION" |
		python3 -c 'import json,sys; name=sys.argv[1]; print(next((a["digest"].removeprefix("sha256:") for a in json.load(sys.stdin)["assets"] if a["name"] == name), ""))' "$archive_name")"
	actual="$(shasum -a 256 "$archive" | awk '{ print $1 }')"
	[[ -n "$expected" ]] || fail "could not read the Caddy asset digest from GitHub"
	[[ "$expected" == "$actual" ]] || fail "Caddy checksum mismatch; delete $archive and retry"
	tar -xzf "$archive" -C "$(dirname "$CADDY_BIN")" caddy
	chmod +x "$CADDY_BIN"
fi

if ! XDG_DATA_HOME="$STATE_DIR/caddy/data" XDG_CONFIG_HOME="$STATE_DIR/caddy/config" \
	"$CADDY_BIN" validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then
	fail "Caddy rejected deploy/Caddyfile"
fi

if [[ $SKIP_BUILD -eq 0 ]]; then
	echo "building frontend..."
	(
		cd "$FRONTEND_DIR"
		VITE_API_URL= VITE_WS_URL= VITE_PUBLIC_BASE_URL="$PUBLIC_URL" npm run build
	)
elif [[ ! -f "$FRONTEND_DIR/dist/index.html" ]]; then
	fail "frontend/dist is missing; rerun without --skip-build"
fi

echo "starting backend..."
(
	cd "$BACKEND_DIR"
	nohup "$BACKEND_DIR/venv/bin/python" -m uvicorn app.main:app \
		--host 127.0.0.1 --port 8000 >"$BACKEND_LOG" 2>&1 &
	echo $! >"$BACKEND_PID_FILE"
)
STARTED_BACKEND=1
if ! curl -fsS --retry 60 --retry-delay 1 --retry-all-errors http://127.0.0.1:8000/health >/dev/null 2>&1; then
	fail "backend did not become healthy; see $BACKEND_LOG"
fi

echo "starting Caddy..."
(
	cd "$ROOT_DIR"
	XDG_DATA_HOME="$STATE_DIR/caddy/data" XDG_CONFIG_HOME="$STATE_DIR/caddy/config" \
		nohup "$CADDY_BIN" run --config "$CADDYFILE" --adapter caddyfile >"$CADDY_LOG" 2>&1 &
	echo $! >"$CADDY_PID_FILE"
)
STARTED_CADDY=1
if ! curl -fsS --retry 30 --retry-delay 1 --retry-all-errors http://127.0.0.1:8080/health >/dev/null 2>&1; then
	fail "Caddy did not become healthy; see $CADDY_LOG"
fi

echo "enabling Tailscale Serve..."
tailscale serve --bg --https=443 http://127.0.0.1:8080 >/dev/null
STARTED_SERVE=1
if ! curl -fsS --retry 30 --retry-delay 1 --retry-all-errors "$PUBLIC_URL/health" >/dev/null 2>&1; then
	fail "HTTPS check failed; confirm HTTPS certificates are enabled for the tailnet"
fi

trap - EXIT
echo
echo "BananaVision is available to tailnet devices:"
echo "  $PUBLIC_URL/"
echo "Loopback only: http://127.0.0.1:8080"
echo "Logs: $BACKEND_LOG $CADDY_LOG"
echo "Stop: $ROOT_DIR/deploy/stop-mac-tailnet.sh"
