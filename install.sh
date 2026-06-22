#!/usr/bin/env bash
#
# CompanionAI one-shot installer.
#   curl -fsSL <raw-url>/install.sh | bash
#
# Installs Docker + the Compose plugin if missing, fetches the code, asks you a
# couple of questions (press Enter for defaults), then builds and launches
# everything — including the watchdog and the local models.
#
set -euo pipefail

REPO="${COMPANION_REPO:-https://github.com/taamrove/companionai.git}"
BRANCH="${COMPANION_BRANCH:-claude/local-openhuman-alternative-7r03zk}"
DIR="${COMPANION_DIR:-$HOME/companionai}"

SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

say()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }

# Prompt the user even when piped through `curl | bash` (reads the terminal).
ask() {  # ask "Prompt" "default" -> prints the answer
  local prompt="$1" def="${2:-}" ans=""
  if [ -r /dev/tty ]; then
    printf '\033[1m%s\033[0m ' "$prompt" > /dev/tty
    read -r ans < /dev/tty || ans=""
  fi
  printf '%s' "${ans:-$def}"
}

# ── 1. Docker ───────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker…"
  curl -fsSL https://get.docker.com | $SUDO sh
fi

# ── 2. Docker Compose v2 plugin (Unraid & some distros lack it) ─────
if ! docker compose version >/dev/null 2>&1; then
  say "Installing the Docker Compose plugin…"
  mkdir -p "$HOME/.docker/cli-plugins"
  curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
    -o "$HOME/.docker/cli-plugins/docker-compose"
  chmod +x "$HOME/.docker/cli-plugins/docker-compose"
fi
docker compose version >/dev/null

# ── 3. Code ─────────────────────────────────────────────────────────
if [ -d "$DIR/.git" ]; then
  say "Updating existing install in $DIR"
  git -C "$DIR" fetch origin "$BRANCH" --depth 1 || true
  git -C "$DIR" checkout "$BRANCH" 2>/dev/null || true
  git -C "$DIR" pull --ff-only || true
else
  say "Cloning into $DIR"
  git clone --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

# ── 4. Configure (.env) ─────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  say "Quick setup — press Enter to accept the default in [brackets]."
  KEY="$(ask 'Anthropic API key for cloud heavy-lifting (blank = fully local):' '')"
  SI="$(ask  'Enable self-improvement + watchdog? [Y/n]:' 'Y')"
  sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${KEY}|" .env
  case "$SI" in
    [Nn]*) ;;
    *) sed -i "s|^SELFIMPROVE_ENABLED=.*|SELFIMPROVE_ENABLED=true|" .env
       sed -i "s|^SELF_CONFIRM_SECONDS=.*|SELF_CONFIRM_SECONDS=0|" .env ;;
  esac
else
  say "Found an existing .env — keeping your settings."
  NEWKEY="$(ask 'Update Anthropic API key? (Enter to keep current):' '')"
  [ -n "$NEWKEY" ] && sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${NEWKEY}|" .env
fi

# Generate an API token if one isn't set yet.
if ! grep -q '^API_TOKEN=..*' .env; then
  TOKEN="$(openssl rand -hex 24 2>/dev/null || date +%s%N | sha256sum | head -c 48)"
  sed -i "s|^API_TOKEN=.*|API_TOKEN=${TOKEN}|" .env
fi
# Clear a leftover placeholder key so it cleanly runs local instead of erroring.
sed -i 's|^ANTHROPIC_API_KEY=sk-ant-paste.*|ANTHROPIC_API_KEY=|' .env

# Watchdog only when self-improvement is on.
PROFILE=""
grep -q '^SELFIMPROVE_ENABLED=true' .env && PROFILE="--profile watchdog"

# ── 5. Launch ───────────────────────────────────────────────────────
say "Building and starting (first run downloads images — give it a minute)…"
docker compose $PROFILE up -d --build

# ── 6. Local models ─────────────────────────────────────────────────
PULL="$(ask 'Download local model llama3.2 + embeddings now (~2 GB)? [Y/n]:' 'Y')"
case "$PULL" in
  [Nn]*) warn "Skipped. Pull later with: docker compose exec ollama ollama pull llama3.2" ;;
  *) say "Waiting for Ollama to come up…"
     tries=0
     until docker compose exec -T ollama ollama list >/dev/null 2>&1 || [ "$tries" -ge 30 ]; do
       sleep 2; tries=$((tries + 1))
     done
     say "Pulling models (this can take a few minutes)…"
     docker compose exec -T ollama ollama pull llama3.2 || true
     docker compose exec -T ollama ollama pull nomic-embed-text || true ;;
esac

# ── 7. Status ───────────────────────────────────────────────────────
sleep 3
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-localhost}"
TOKEN="$(grep '^API_TOKEN=' .env | cut -d= -f2)"
say "CompanionAI is up."
curl -s localhost:8080/health || warn "Health check didn't respond yet — try in a few seconds."
echo
echo "  Open:  http://${IP}:8080/?token=${TOKEN}"
echo "  API token: ${TOKEN}"
echo "  Logs:  cd ${DIR} && docker compose logs -f brain"
echo
echo "  Tip: to reach it from your phone without opening ports, run on this box:"
echo "       curl -fsSL https://tailscale.com/install.sh | sh && ${SUDO} tailscale up"
