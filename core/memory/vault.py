"""Obsidian-style Markdown vault.

Every memory is also written to a human-browsable/editable Markdown file so the
user owns their data as plain text, exactly like OpenHuman's "Memory Tree".
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


def _slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len] or "note").rstrip("-")


class Vault:
    """Writes memories as Markdown notes under ``<data>/vault/``."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_note(self, kind: str, text: str, tags: list[str] | None = None) -> str:
        """Persist a memory as a Markdown note; returns the relative path."""
        now = datetime.now(timezone.utc)
        folder = self.root / kind
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{now:%Y%m%d-%H%M%S}-{_slugify(text)}.md"
        path = folder / name

        front_matter = [
            "---",
            f"created: {now.isoformat()}",
            f"kind: {kind}",
            f"tags: [{', '.join(tags or [])}]",
            "---",
            "",
            text.strip(),
            "",
        ]
        path.write_text("\n".join(front_matter), encoding="utf-8")
        return str(path.relative_to(self.root))

    def list_notes(self, limit: int = 100) -> list[dict]:
        notes = sorted(
            self.root.rglob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        out = []
        for p in notes[:limit]:
            out.append(
                {
                    "path": str(p.relative_to(self.root)),
                    "modified": datetime.fromtimestamp(
                        p.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "preview": p.read_text(encoding="utf-8")[:200],
                }
            )
        return out

    def read_note(self, rel_path: str) -> str | None:
        # Confine reads to the vault root — reject traversal.
        target = (self.root / rel_path).resolve()
        if not target.is_relative_to(self.root.resolve()) or not target.is_file():
            return None
        return target.read_text(encoding="utf-8")
