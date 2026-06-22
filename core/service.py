"""The Companion service — orchestrates memory, RAG, and hybrid inference.

This is the single entry point the API calls for a chat turn. It:
  1. records the user turn,
  2. recalls relevant long-term memories (RAG),
  3. routes to local (Ollama) or cloud (Claude),
  4. on the cloud path, lets Claude call tools to search/save memory,
  5. records the assistant turn and returns the reply.
"""

from __future__ import annotations

import json

from core.config import Settings
from core.llm.router import LLMRouter
from core.memory.store import MemoryStore
from core.rag.retriever import Retriever
from core.selfimprove import SkillRegistry

# The persona (system prompt) is now a *userland skill* loaded from the registry,
# so the companion can revise its own character under the self-improvement
# guardrails. See skills/persona/active.md.

# Used for the instant "warm" reply from the local model while the cloud brain
# works on the considered answer. Keep it short and human — it's a holding turn.
WARM_ADDENDUM = """

You are giving an IMMEDIATE first reply while a more capable model works on a \
thorough answer in the background. Respond in 1-2 short sentences: acknowledge \
the request and share a quick first thought. Do not attempt the full answer — \
a better one is coming right behind you."""

# Tool the cloud brain can call to persist a durable memory.
SAVE_MEMORY_TOOL = {
    "name": "save_memory",
    "description": (
        "Persist a durable fact about the user to long-term memory so you can "
        "recall it in future conversations. Use for stable preferences, personal "
        "facts, people, projects, and goals — not for trivia or one-off remarks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The fact to remember, written as a clear statement.",
            },
            "kind": {
                "type": "string",
                "enum": ["fact", "preference", "person", "project", "goal"],
                "description": "Category of memory.",
            },
        },
        "required": ["text"],
    },
}

# Tool the cloud brain can call to revise one of its own userland skills. Only
# offered when the master self-improvement switch is on; every call still goes
# through the kernel's health gate + auto-rollback (see core/selfimprove/).
REVISE_SKILL_TOOL = {
    "name": "revise_skill",
    "description": (
        "Improve one of your own behaviours by submitting a new version of a "
        "skill. Changes are health-checked and automatically rolled back if they "
        "break anything. Use sparingly, only when you can clearly state why the "
        "revision is better."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill": {"type": "string", "enum": ["persona", "routing"]},
            "content": {
                "type": "string",
                "description": "The complete new content for the skill (full "
                "replacement, not a diff).",
            },
            "reason": {"type": "string", "description": "Why this is an improvement."},
        },
        "required": ["skill", "content", "reason"],
    },
}


class Companion:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = MemoryStore(settings.db_path, settings.vault_path)
        self.registry = SkillRegistry(settings)
        self.router = LLMRouter(settings, self.registry)
        self.retriever = Retriever(self.store, self.router)

    async def _remember(self, session_id: str, text: str, kind: str = "fact") -> None:
        embedding = await self.router.embed(text)
        self.store.add_memory(session_id, text, kind=kind, embedding=embedding)

    def _build_system(self, recalled: list[dict]) -> str:
        persona = self.registry.load("persona")  # mutable skill, self-healing
        if not recalled:
            return persona
        lines = "\n".join(f"- ({m['kind']}) {m['text']}" for m in recalled)
        return f"{persona}\n\nRecalled memories:\n{lines}"

    async def chat(self, session_id: str, message: str) -> dict:
        self.store.add_turn(session_id, "user", message)

        recalled = await self.retriever.search(
            message, session_id=session_id, top_k=self.settings.rag_top_k
        )
        system = self._build_system(recalled)
        history = self.store.recent_turns(session_id, limit=20)

        if self.router.use_cloud(message):
            reply, engine = await self._chat_cloud(session_id, system, history)
        else:
            reply, engine = await self._chat_local(session_id, system, history, message)

        self.store.add_turn(session_id, "assistant", reply)
        return {
            "reply": reply,
            "engine": engine,
            "recalled": recalled,
            "model": (
                self.settings.cloud_model if engine == "cloud" else self.settings.local_model
            ),
        }

    async def chat_stream(self, session_id: str, message: str):
        """Two-phase chat as an async generator of events.

        For heavy turns this keeps the dialogue *warm*: the local model answers
        instantly so the user is never staring at a blank screen, then the cloud
        brain's considered reply arrives behind it. Light turns just yield one
        local reply.

        Yields dicts: {"phase": "warm"|"final", "engine", "reply", ...}.
        """
        self.store.add_turn(session_id, "user", message)

        recalled = await self.retriever.search(
            message, session_id=session_id, top_k=self.settings.rag_top_k
        )
        system = self._build_system(recalled)
        history = self.store.recent_turns(session_id, limit=20)

        going_cloud = self.router.use_cloud(message)

        # Light turn → single local reply.
        if not going_cloud:
            reply, engine = await self._chat_local(session_id, system, history, message)
            self.store.add_turn(session_id, "assistant", reply)
            yield {"phase": "final", "engine": engine, "reply": reply,
                   "model": self.settings.local_model, "recalled": recalled}
            return

        # Heavy turn → warm local reply first (best-effort), then cloud.
        if await self.router.local.healthy():
            try:
                warm = await self.router.local.chat(system + WARM_ADDENDUM, history)
                yield {"phase": "warm", "engine": "local",
                       "reply": warm.strip(), "model": self.settings.local_model}
            except Exception:
                pass  # warm phase is best-effort; never block the real answer

        reply, engine = await self._chat_cloud(session_id, system, history)
        self.store.add_turn(session_id, "assistant", reply)
        yield {"phase": "final", "engine": engine, "reply": reply,
               "model": self.settings.cloud_model, "recalled": recalled}

    async def _chat_cloud(
        self, session_id: str, system: str, history: list[dict]
    ) -> tuple[str, str]:
        assert self.router.cloud is not None
        cloud = self.router.cloud
        # Claude needs structured content; history is plain strings.
        messages: list[dict] = [
            {"role": h["role"], "content": h["content"]} for h in history
        ]

        # Self-improvement is only offered when the human master switch is on.
        tools = [SAVE_MEMORY_TOOL]
        if self.registry.enabled:
            tools.append(REVISE_SKILL_TOOL)

        # Tool-use loop: keep going until Claude stops calling tools.
        for _ in range(5):
            resp = await cloud.create(system, messages, tools=tools)
            if resp.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": await self._run_tool(session_id, block),
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or "…", "cloud"

    async def _run_tool(self, session_id: str, block) -> str:
        """Dispatch a single tool call from the cloud brain."""
        if block.name == "save_memory":
            await self._remember(
                session_id, block.input["text"], block.input.get("kind", "fact")
            )
            return "Saved."
        if block.name == "revise_skill":
            # Goes through the kernel's guarded path: health gate + auto-rollback.
            result = self.registry.apply(
                block.input["skill"],
                block.input["content"],
                author="companion",
                reason=block.input.get("reason", ""),
            )
            return json.dumps(result)
        return f"Unknown tool: {block.name}"

    async def _chat_local(
        self, session_id: str, system: str, history: list[dict], message: str
    ) -> tuple[str, str]:
        # Local models here don't run the tool loop; use a lightweight heuristic
        # so "remember ..." still persists a memory.
        lowered = message.lower().strip()
        if lowered.startswith(("remember ", "note that ", "don't forget ")):
            fact = message.split(" ", 1)[1] if " " in message else message
            await self._remember(session_id, fact, kind="fact")

        try:
            reply = await self.router.local.chat(system, history)
            return reply.strip() or "…", "local"
        except Exception as exc:  # Ollama unreachable / model not pulled
            return (
                "I couldn't reach the local model "
                f"({self.settings.local_model}). Is Ollama running and the model "
                f"pulled? Error: {exc}",
                "local",
            )
