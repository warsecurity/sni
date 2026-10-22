#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

RED='\033[1;31m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'
LOG_FILE="$SCRIPT_DIR/logs.txt"

cleanup_stale() {
    screen -S vpn_tunnel -X quit >/dev/null 2>&1 || true
    screen -S vpn_ssh -X quit >/dev/null 2>&1 || true
    # Compatibility cleanup for sessions created by the original script.
    screen -S nohub -X quit >/dev/null 2>&1 || true
    pkill -f "[p]ython3? .*${SCRIPT_DIR}/tunnel.py" 2>/dev/null || true
    pkill -f "[p]ython3? .*${SCRIPT_DIR}/ssh.py" 2>/dev/null || true
    pkill -f '[b]advpn-tun2socks.*--tundev tun0' 2>/dev/null || true
    pkill -f '[d]ns2socks.*127\.0\.0\.1:1080' 2>/dev/null || true
    ip link set tun0 down 2>/dev/null || true
    ip tuntap del dev tun0 mode tun 2>/dev/null || true
}

cleanup_exit() {
    echo -e "${YELLOW}Stopping VPN processes...${RESET}"
    cleanup_stale
}
trap cleanup_exit EXIT INT TERM

for cmd in python3 screen ssh sshpass ip grep; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo -e "${RED}Missing required command: $cmd${RESET}"
        exit 1
    }
done

[[ $EUID -eq 0 ]] || {
    echo -e "${RED}Run this script with sudo/root privileges.${RESET}"
    exit 1
}
[[ -f settings.ini ]] || { echo -e "${RED}settings.ini was not found.${RESET}"; exit 1; }

# Critical fix: old success lines must not be reused by a later run.
cleanup_stale
: > "$LOG_FILE"

echo -e "${GREEN}Choose Connection Method:${RESET}"
echo "0 - SSH Direct"
echo "1 - PAYLOAD"
echo "2 - SSL"
echo "3 - SSL+PAYLOAD"
read -r -p "Enter choice number: " mode
[[ "$mode" =~ ^[0-3]$ ]] || { echo -e "${RED}Wrong choice.${RESET}"; exit 1; }

python3 - "$mode" <<'PY'
import configparser, pathlib, sys
path = pathlib.Path('settings.ini')
cfg = configparser.ConfigParser()
with path.open() as f:
    cfg.read_file(f)
if not cfg.has_section('mode'):
    cfg.add_section('mode')
cfg['mode']['connection_mode'] = sys.argv[1]
with path.open('w') as f:
    cfg.write(f)
PY

# Start the local CONNECT endpoint and wait until port 9092 is listening.
screen -dmS vpn_tunnel bash -lc "cd '$SCRIPT_DIR' && exec python3 '$SCRIPT_DIR/tunnel.py'"
for _ in $(seq 1 10); do
    ss -ltn 2>/dev/null | grep -qE '127\.0\.0\.1:9092|0\.0\.0\.0:9092|\*:9092' && break
    sleep 1
done
if ! ss -ltn 2>/dev/null | grep -q ':9092'; then
    echo -e "${RED}Local tunnel did not start on port 9092.${RESET}"
    cat "$LOG_FILE"
    exit 1
fi

ssh_mode=1
[[ "$mode" == 2 || "$mode" == 3 ]] && ssh_mode=2
screen -dmS vpn_ssh bash -lc "cd '$SCRIPT_DIR' && exec python3 '$SCRIPT_DIR/ssh.py' '$ssh_mode'"

echo -e "${YELLOW}Waiting for SSH authentication...${RESET}"
connected=0
for _ in $(seq 1 40); do
    if grep -q 'CONNECTED SUCCESSFULLY' "$LOG_FILE" 2>/dev/null; then
        connected=1
        break
    fi
    if grep -qE 'Permission denied|Connection closed|Connection refused|timed out|SSH ERROR' "$LOG_FILE" 2>/dev/null; then
        break
    fi
    sleep 1
done

cat "$LOG_FILE"
if [[ "$connected" -ne 1 ]]; then
    echo -e "${RED}SSH did not authenticate. The message is not necessarily a settings.ini error.${RESET}"
    echo "Netcat success only proves that the TCP port accepted a connection."
    exit 1
fi

if ! ss -ltn 2>/dev/null | grep -q ':1080'; then
    echo -e "${RED}SSH authenticated, but SOCKS port 1080 is not listening.${RESET}"
    exit 1
fi

echo -e "${GREEN}SSH and SOCKS are ready. Starting tun2socks...${RESET}"
chmod +x "$SCRIPT_DIR/proxification.sh"
"$SCRIPT_DIR/proxification.sh"
