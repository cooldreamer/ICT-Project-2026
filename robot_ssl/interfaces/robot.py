"""Replaceable robot head/camera control interface (console and HTTP adapters)."""
from __future__ import annotations
import json
import logging
import time
from urllib.request import Request, urlopen


class RobotMovementInterface:
    def orient_camera(self, azimuth_degrees: float, attention_score: float, reason: str = "addressed_speech") -> None:
        raise NotImplementedError

    def set_alertness(self, state: str, detail: str = "") -> None:
        raise NotImplementedError


class ConsoleRobotInterface(RobotMovementInterface):
    """Safe default: logs intended motions but never moves physical hardware."""
    def orient_camera(self, azimuth_degrees: float, attention_score: float, reason: str = "addressed_speech") -> None:
        logging.info(
            "[SIMULATED ROBOT] orient camera/head to %+.1f° (confidence %.2f; %s)",
            azimuth_degrees, attention_score, reason,
        )

    def set_alertness(self, state: str, detail: str = "") -> None:
        logging.info("[ROBOT ALERTNESS] %s %s", state, detail)


class HttpRobotInterface(RobotMovementInterface):
    """POST generic JSON commands to a robot gateway; adapt the schema to your robot."""
    def __init__(self, endpoint: str, timeout_seconds: float = 1.5) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def _post(self, payload: dict) -> None:
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Robot endpoint returned HTTP {response.status}")
        except Exception:
            logging.exception("Robot endpoint request failed")

    def orient_camera(self, azimuth_degrees: float, attention_score: float, reason: str = "addressed_speech") -> None:
        self._post({
            "command": "orient_camera",
            "azimuth_degrees": float(azimuth_degrees),
            "attention_score": float(attention_score),
            "reason": reason,
            "timestamp_unix": time.time(),
        })

    def set_alertness(self, state: str, detail: str = "") -> None:
        self._post({"command": "set_alertness", "state": state, "detail": detail, "timestamp_unix": time.time()})
