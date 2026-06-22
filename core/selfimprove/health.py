"""Health checks gating skill activation.

A revision is only kept if it passes the check for its skill. Checks are
deliberately cheap and conservative — their job is to catch a broken or unsafe
revision *before* it can degrade the live companion. Anything that fails here is
auto-rolled-back to the last-known-good version.
"""

from __future__ import annotations

import json

# Obvious credential-shaped strings that must never appear in a skill body.
_SECRET_MARKERS = ("sk-ant-", "ANTHROPIC_API_KEY", "BEGIN PRIVATE KEY", "password=")


def _no_secrets(text: str) -> tuple[bool, str]:
    low = text.lower()
    for marker in _SECRET_MARKERS:
        if marker.lower() in low:
            return False, f"contains secret-shaped marker: {marker}"
    return True, "ok"


def check_persona(content: str) -> tuple[bool, str]:
    if not content or not content.strip():
        return False, "persona is empty"
    if len(content) > 20000:
        return False, "persona too long (>20k chars)"
    return _no_secrets(content)


def check_routing(content: str) -> tuple[bool, str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}"
    if not isinstance(data.get("length_threshold"), int):
        return False, "length_threshold must be an int"
    hints = data.get("heavy_hints")
    if not isinstance(hints, list) or not all(isinstance(h, str) for h in hints):
        return False, "heavy_hints must be a list of strings"
    return _no_secrets(content)


CHECKS = {
    "persona": check_persona,
    "routing": check_routing,
}


def run_check(skill: str, content: str) -> tuple[bool, str]:
    check = CHECKS.get(skill)
    if check is None:
        # Unknown skills get the conservative default: reject.
        return False, f"no health check registered for skill '{skill}'"
    return check(content)
