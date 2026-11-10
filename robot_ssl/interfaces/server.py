"""Optional outbound event integration for a user-supplied server endpoint."""
from __future__ import annotations
import json
import logging
from urllib.request import Request, urlopen


class ServerInterface:
    """Optionally forward perception events to a user-provided HTTP endpoint."""

    def __init__(self, endpoint: str | None, timeout_seconds: float = 1.5) -> None:
        """Set the destination endpoint and HTTP timeout.

        Parameters:
            * endpoint : Optional server URL for perception-event POSTs.
            * timeout_seconds : Maximum time to wait for each HTTP request.

        Returns:
            None.
        """
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def send_event(self, event: dict) -> None:
        """POST an event as JSON when an endpoint has been configured.

        Parameters:
            * event : Perception-event dictionary to send.

        Notes:
            HTTP errors and other request failures are logged and suppressed.
            An HTTP error response is first represented internally as a
            ``RuntimeError``.

        Returns:
            None.
        """
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
