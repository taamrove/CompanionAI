"""Self-improvement subsystem (kernel-owned, immutable to the AI).

Lets the companion revise its own *userland* skills (persona, routing, …) with
hard safety guarantees the AI cannot bypass:

  * every change is versioned and reversible
  * every activation is health-checked, with automatic rollback on failure
  * a runtime fallback chain (active → last-known-good → shipped → baked-in)
    means the companion never stops functioning
  * a master kill switch (human-only) gates whether any of this is allowed
  * every action is written to an append-only audit log
"""

from core.selfimprove.registry import SkillRegistry

__all__ = ["SkillRegistry"]
