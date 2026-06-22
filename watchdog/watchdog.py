"""CompanionAI watchdog — external supervisor for the brain container.

Runs in its own container so it survives the brain crashing. It owns two jobs:

  1. Liveness recovery — poll the brain's /health; if it stops responding,
     restart it (which triggers the brain's boot-time crash-rollback of any bad
     self-applied change).

  2. Self-improvement lifecycle — when the brain has a *staged* skill revision,
     the watchdog TRIGGERS the apply (a restart), then watches health through a
     probation window:
        healthy throughout  → POST /selfimprove/confirm  (promote to good)
        crash / unhealthy   → restart  (brain rolls back to last-known-good)

The component being improved never decides its own change succeeded — the
supervisor outside it does.
"""

from __future__ import annotations

import os
import subprocess
import time

import httpx

BRAIN_URL = os.environ.get("BRAIN_URL", "http://brain:8080").rstrip("/")
TARGET = os.environ.get("TARGET_CONTAINER", "companionai-brain")
API_TOKEN = os.environ.get("API_TOKEN", "")
DOCKER_SOCK = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
# Restart mechanism. If RESTART_CMD is set (e.g. "systemctl restart companionai")
# the watchdog runs it directly — for native/systemd installs with no Docker.
# Otherwise it restarts the brain container via the Docker socket.
RESTART_CMD = os.environ.get("RESTART_CMD", "")

INTERVAL = int(os.environ.get("INTERVAL", "10"))          # seconds between polls
FAIL_THRESHOLD = int(os.environ.get("FAIL_THRESHOLD", "3"))  # down polls → restart
PROBATION = int(os.environ.get("PROBATION", "45"))        # healthy window to confirm
AUTO_APPLY = os.environ.get("AUTO_APPLY", "true").lower() == "true"

_auth = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
_docker = None


def _docker_client() -> httpx.Client:
    global _docker
    if _docker is None:
        _docker = httpx.Client(
            transport=httpx.HTTPTransport(uds=DOCKER_SOCK),
            base_url="http://docker", timeout=30,
        )
    return _docker


def log(msg: str) -> None:
    print(f"[watchdog] {msg}", flush=True)


def healthy() -> bool:
    try:
        return httpx.get(f"{BRAIN_URL}/health", headers=_auth, timeout=5).status_code == 200
    except Exception:
        return False


def status() -> dict | None:
    try:
        r = httpx.get(f"{BRAIN_URL}/selfimprove/status", headers=_auth, timeout=5)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def confirm() -> None:
    try:
        httpx.post(f"{BRAIN_URL}/selfimprove/confirm", headers=_auth, timeout=10)
        log("confirmed: applied version promoted to last-known-good")
    except Exception as exc:
        log(f"confirm failed: {exc}")


def restart(reason: str) -> None:
    log(f"restarting brain ({reason})")
    try:
        if RESTART_CMD:
            subprocess.run(RESTART_CMD, shell=True, check=False)
        else:
            _docker_client().post(f"/containers/{TARGET}/restart")
    except Exception as exc:
        log(f"restart failed: {exc}")


def has_staged(st: dict | None) -> bool:
    return bool(st) and any(s.get("staged") is not None for s in st.get("skills", []))


def main() -> None:
    log(f"watching {BRAIN_URL} → container {TARGET}")
    fails = 0
    probation_until = 0.0  # >0 while we're vetting a freshly applied change

    while True:
        up = healthy()

        if not up:
            fails += 1
            log(f"unhealthy ({fails}/{FAIL_THRESHOLD})")
            if fails >= FAIL_THRESHOLD:
                restart("liveness failure")
                fails = 0
                probation_until = 0.0  # restart will roll back; abandon probation
                time.sleep(INTERVAL * 2)  # cool-down for reboot
            time.sleep(INTERVAL)
            continue

        fails = 0
        now = time.time()

        # In a probation window after applying a change?
        if probation_until:
            if now >= probation_until:
                confirm()
                probation_until = 0.0
            time.sleep(INTERVAL)
            continue

        # Healthy and idle → if a change is staged, trigger the apply.
        if AUTO_APPLY and has_staged(status()):
            log("staged revision detected → triggering apply via restart")
            restart("apply staged revision")
            probation_until = time.time() + PROBATION + INTERVAL  # +reboot slack
            time.sleep(INTERVAL * 2)
            continue

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
