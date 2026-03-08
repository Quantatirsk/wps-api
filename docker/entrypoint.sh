#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/workspace/runtime}"
export WPS_FONT_DIR="${WPS_FONT_DIR:-/usr/local/share/fonts/zhFonts}"
export XORG_CONFIG_PATH="${XORG_CONFIG_PATH:-/etc/X11/xorg-dummy.conf}"
export XORG_LOG_PATH="${XORG_LOG_PATH:-/tmp/Xorg.log}"

mkdir -p "$XDG_RUNTIME_DIR" /var/run/dbus /workspace/jobs
chmod 700 "$XDG_RUNTIME_DIR"

if [[ ! -s /etc/machine-id ]]; then
  dbus-uuidgen > /etc/machine-id
fi

dbus-uuidgen --ensure=/etc/machine-id

if [[ -d "$WPS_FONT_DIR" ]]; then
  fc-cache -f "$WPS_FONT_DIR" >/dev/null 2>&1 || true
fi
fc-cache -f >/dev/null 2>&1 || true
ldconfig >/dev/null 2>&1 || true

DISPLAY_NUMBER="${DISPLAY#:}"
rm -f "/tmp/.X${DISPLAY_NUMBER}-lock" "/tmp/.X11-unix/X${DISPLAY_NUMBER}"
mkdir -p /tmp/.X11-unix

Xorg "$DISPLAY" \
  -config "$XORG_CONFIG_PATH" \
  -logfile "$XORG_LOG_PATH" \
  -noreset \
  +extension GLX \
  +extension RANDR \
  +extension RENDER \
  -nolisten tcp &
XORG_PID=$!

eval "$(dbus-launch --sh-syntax)"

cleanup() {
  kill "$XORG_PID" 2>/dev/null || true
  if [[ -n "${DBUS_SESSION_BUS_PID:-}" ]]; then
    kill "$DBUS_SESSION_BUS_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT TERM INT

for _ in $(seq 1 20); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    exec "$@"
  fi
  sleep 1
done

echo "Xorg failed to become ready; see $XORG_LOG_PATH" >&2
if [[ -f "$XORG_LOG_PATH" ]]; then
  tail -n 80 "$XORG_LOG_PATH" >&2 || true
fi
exit 1
