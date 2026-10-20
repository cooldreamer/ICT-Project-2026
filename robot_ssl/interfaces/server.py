"""Optional outbound event integration for a user-supplied server endpoint."""
from __future__ import annotations
import json
import logging
from urllib.request import Request, urlopen


class ServerInterface:
    def __init__(self, endpoint: str | None, timeout_seconds: float = 1.5) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def send_event(self, event: dict) -> None:
        if not self.endpoint:
            return
        request = Request(
            self.endpoint,
            data=json.dumps(event, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Server endpoint returned HTTP {response.status}")
        except Exception:
            logging.exception("Event could not be sent to configured server")
