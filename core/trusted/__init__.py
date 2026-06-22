"""The trusted root — the irreducible, human-only foundation.

Nothing in this package may be modified by the AI. It holds the partition
manifest and the guard the self-improvement path must consult before touching
anything. A self-modifying system can roll back a change to anything EXCEPT the
mechanism that performs the rollback — that mechanism lives here (and in
core/selfimprove + watchdog/), and stays human-controlled by design.
"""

from core.trusted.manifest import is_mutable, is_trusted

__all__ = ["is_mutable", "is_trusted"]
