"""Gmail connector (skeleton).

The framework is here; the OAuth flow + Gmail API calls are stubbed so the
shape is clear and the route works end-to-end without credentials yet.

To finish:
  1. Add an OAuth flow (google-auth-oauthlib) and store the token under
     ``<data>/connectors/gmail/token.json``.
  2. In ``sync`` call the Gmail API, summarize recent threads (route the
     summarization through the cloud brain), and write one memory per useful
     thread via ``self.store.add_memory(...)``.
"""

from __future__ import annotations

from core.config import get_settings
from core.integrations.base import Connector


class GmailConnector(Connector):
    name = "gmail"

    def _token_path(self):
        p = get_settings().data_path / "connectors" / "gmail"
        p.mkdir(parents=True, exist_ok=True)
        return p / "token.json"

    async def configured(self) -> bool:
        return self._token_path().exists()

    async def sync(self, session_id: str) -> int:
        if not await self.configured():
            raise RuntimeError(
                "Gmail is not connected yet. Complete the OAuth flow first "
                "(see app/integrations/gmail.py)."
            )
        # TODO: fetch recent threads, summarize, and write memories.
        return 0
