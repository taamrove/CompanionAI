#!/usr/bin/env bash
#
# CompanionAI native installer (NO Docker) — for a Debian/Ubuntu box or LXC.
# Installs Ollama, a Python venv, and systemd services for the brain + watchdog.
#
#   curl -fsSL <raw-url>/install-native.sh | bash
#
set -euo pipefail

REPO="${COMPANION_REPO:-https://github.com/taamrove/companionai.git}"
BRANCH="${COMPANION_BRANCH:-claude/local-openhuman-alternative-7r03zk}"
DIR="${COMPANION_DIR:-/opt/companionai}"

SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
say()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
ask() {  # ask "Prompt" "default"
  local prompt="$1" def="${2:-}" ans=""
  if [ -r /dev/tty ]; then
    printf '\033[1m%s\033[0m ' "$prompt" > /dev/tty
    read -r ans < /dev/tty || ans=""
  fi
  printf '%s' "${ans:-$def}"
}

# ── 1. System packages ──────────────────────────────────────────────
say "Installing system packages…"
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq python3 python3-venv python3-pip git curl openssl ca-certificates zstd

# ── 2. Ollama (native systemd service) ──────────────────────────────
if ! command -v ollama >/dev/null 2>&1; then
  say "Installing Ollama…"
  curl -fsSL https://ollama.com/install.sh | $SUDO sh
fi
$SUDO systemctl enable --now ollama 2>/dev/null || true

# ── 3. Code ─────────────────────────────────────────────────────────
if [ -d "$DIR/.git" ]; then
  say "Updating existing install in $DIR"
  $SUDO git -C "$DIR" fetch origin "$BRANCH" --depth 1 || true
  $SUDO git -C "$DIR" checkout "$BRANCH" 2>/dev/null || true
  $SUDO git -C "$DIR" pull --ff-only || true
else
  say "Cloning into $DIR"
  $SUDO git clone --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

# ── 4. Python venv ──────────────────────────────────────────────────
say "Setting up the Python environment…"
$SUDO python3 -m venv "$DIR/.venv"
$SUDO "$DIR/.venv/bin/pip" install -q -U pip
$SUDO "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"

# ── 5. Configure (.env) ─────────────────────────────────────────────
if [ ! -f "$DIR/.env" ]; then
  $SUDO cp "$DIR/.env.example" "$DIR/.env"
  say "Quick setup — press Enter to accept the default in [brackets]."
  KEY="$(ask 'Anthropic API key for cloud heavy-lifting (blank = fully local):' "${ANTHROPIC_API_KEY:-}")"
  SI="$(ask  'Enable self-improvement + watchdog? [Y/n]:' 'Y')"
  $SUDO sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${KEY}|" "$DIR/.env"
  case "$SI" in
    [Nn]*) WATCHDOG=0 ;;
    *) $SUDO sed -i "s|^SELFIMPROVE_ENABLED=.*|SELFIMPROVE_ENABLED=true|" "$DIR/.env"
       $SUDO sed -i "s|^SELF_CONFIRM_SECONDS=.*|SELF_CONFIRM_SECONDS=0|" "$DIR/.env"
       WATCHDOG=1 ;;
  esac
else
  say "Found an existing .env — keeping your settings."
  WATCHDOG=1; grep -q '^SELFIMPROVE_ENABLED=true' "$DIR/.env" || WATCHDOG=0
fi

# Native paths: local Ollama, data under the install dir.
$SUDO sed -i "s|^OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://127.0.0.1:11434|" "$DIR/.env"
$SUDO sed -i "s|^DATA_DIR=.*|DATA_DIR=${DIR}/data|" "$DIR/.env"
$SUDO sed -i 's|^ANTHROPIC_API_KEY=sk-ant-paste.*|ANTHROPIC_API_KEY=|' "$DIR/.env"
if ! grep -q '^API_TOKEN=..*' "$DIR/.env"; then
  TOKEN="$(openssl rand -hex 24 2>/dev/null || date +%s%N | sha256sum | head -c 48)"
  $SUDO sed -i "s|^API_TOKEN=.*|API_TOKEN=${TOKEN}|" "$DIR/.env"
fi
TOKEN="$(grep '^API_TOKEN=' "$DIR/.env" | cut -d= -f2)"
$SUDO mkdir -p "$DIR/data"

# ── 6. systemd services ─────────────────────────────────────────────
say "Installing systemd services…"
$SUDO tee /etc/systemd/system/companionai.service >/dev/null <<UNIT
[Unit]
Description=CompanionAI brain
After=network-online.target ollama.service
Wants=network-online.target

[Service]
WorkingDirectory=${DIR}
EnvironmentFile=${DIR}/.env
ExecStart=${DIR}/.venv/bin/uvicorn core.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

if [ "${WATCHDOG:-0}" = "1" ]; then
  $SUDO tee /etc/systemd/system/companionai-watchdog.service >/dev/null <<UNIT
[Unit]
Description=CompanionAI watchdog
After=companionai.service

[Service]
ExecStart=${DIR}/.venv/bin/python ${DIR}/watchdog/watchdog.py
Environment=BRAIN_URL=http://127.0.0.1:8080
Environment=API_TOKEN=${TOKEN}
Environment=RESTART_CMD=systemctl restart companionai
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
fi

$SUDO systemctl daemon-reload
$SUDO systemctl enable --now companionai
[ "${WATCHDOG:-0}" = "1" ] && $SUDO systemctl enable --now companionai-watchdog || true

# ── 7. Local models ─────────────────────────────────────────────────
PULL="$(ask 'Download local model llama3.2 + embeddings now (~2 GB)? [Y/n]:' 'Y')"
case "$PULL" in
  [Nn]*) warn "Skipped. Pull later with: ollama pull llama3.2" ;;
  *) say "Pulling models (this can take a few minutes)…"
     ollama pull llama3.2 || true
     ollama pull nomic-embed-text || true ;;
esac

# ── 8. Status ───────────────────────────────────────────────────────
sleep 3
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-localhost}"
say "CompanionAI is up."
curl -s localhost:8080/health || warn "Health didn't respond yet — check: journalctl -u companionai -e"
echo
echo "  Open:  http://${IP}:8080/?token=${TOKEN}"
echo "  API token: ${TOKEN}"
echo "  Logs:  journalctl -u companionai -f"
echo "  Watchdog logs: journalctl -u companionai-watchdog -f"
