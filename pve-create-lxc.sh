#!/usr/bin/env bash
#
# Create a Debian 12 LXC on a Proxmox VE host and install CompanionAI inside it
# (natively, no Docker). Run this ON THE PROXMOX HOST as root.
#
#   bash <(curl -fsSL <raw-url>/pve-create-lxc.sh)
#
# Optional overrides via env: CTID, HOSTNAME, CORES, MEMORY, DISK, BRIDGE,
# STORAGE (rootfs), ANTHROPIC_API_KEY.
#
set -euo pipefail

BRANCH="${COMPANION_BRANCH:-claude/local-openhuman-alternative-7r03zk}"
RAW="https://raw.githubusercontent.com/taamrove/companionai/${BRANCH}"

HOSTNAME="${HOSTNAME:-companionai}"
CORES="${CORES:-4}"
MEMORY="${MEMORY:-8192}"
DISK="${DISK:-20}"            # GB
BRIDGE="${BRIDGE:-vmbr0}"

say()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this as root on the Proxmox host."
command -v pct >/dev/null 2>&1 || die "'pct' not found — this must run on a Proxmox VE host."

# ── pick a Debian 12 template, download if needed ───────────────────
say "Finding a Debian 12 template…"
pveam update >/dev/null 2>&1 || true
TEMPLATE="$(pveam available --section system 2>/dev/null | awk '/debian-12-standard/{print $2}' | sort -V | tail -1)"
[ -n "$TEMPLATE" ] || die "No debian-12-standard template available via pveam."
TSTORE="$(pvesm status -content vztmpl 2>/dev/null | awk 'NR>1{print $1; exit}')"; TSTORE="${TSTORE:-local}"
if ! pveam list "$TSTORE" 2>/dev/null | grep -q "$TEMPLATE"; then
  say "Downloading $TEMPLATE to $TSTORE…"
  pveam download "$TSTORE" "$TEMPLATE"
fi

# ── pick a rootfs storage ───────────────────────────────────────────
STORAGE="${STORAGE:-$(pvesm status -content rootdir 2>/dev/null | awk 'NR>1{print $1; exit}')}"
[ -n "$STORAGE" ] || die "No storage that supports container rootfs was found."

CTID="${CTID:-$(pvesh get /cluster/nextid)}"

say "Creating LXC $CTID  (host=$HOSTNAME, $CORES cores, ${MEMORY}MB RAM, ${DISK}G on $STORAGE)"
pct create "$CTID" "${TSTORE}:vztmpl/${TEMPLATE}" \
  --hostname "$HOSTNAME" \
  --cores "$CORES" --memory "$MEMORY" --swap 2048 \
  --rootfs "${STORAGE}:${DISK}" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
  --unprivileged 1 --features nesting=1 \
  --onboot 1 --start 1

say "Waiting for the container to get networking…"
IP=""
for _ in $(seq 1 30); do
  IP="$(pct exec "$CTID" -- bash -lc "hostname -I 2>/dev/null | awk '{print \$1}'" 2>/dev/null || true)"
  [ -n "$IP" ] && break
  sleep 2
done
[ -n "$IP" ] || say "Network still pending — install will continue and DHCP should settle."

say "Installing CompanionAI inside container $CTID (no Docker)…"
# The minimal Debian template has no curl — install it before bootstrapping.
pct exec "$CTID" -- bash -lc "apt-get update -qq && apt-get install -y -qq curl ca-certificates"
pct exec "$CTID" -- bash -lc \
  "ANTHROPIC_API_KEY='${ANTHROPIC_API_KEY:-}' bash <(curl -fsSL ${RAW}/install-native.sh)"

say "Done."
echo "  Container: $CTID   IP: ${IP:-<check: pct exec $CTID -- hostname -I>}"
echo "  Enter it:  pct enter $CTID"
echo "  The installer above printed the URL + API token."
