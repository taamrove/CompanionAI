"""Example module: contributes a `get_time` tool to the companion.

Demonstrates the plug-in contract — it touches only the permission-gated host
API, never the core. Use it as a template for new modules.
"""

from datetime import datetime, timezone


def setup(host):
    host.log("clock module loaded")
    host.register_tool(
        {
            "name": "get_time",
            "description": "Get the current UTC date and time (ISO 8601).",
            "input_schema": {"type": "object", "properties": {}},
        },
        handler=lambda _input: datetime.now(timezone.utc).isoformat(),
    )
