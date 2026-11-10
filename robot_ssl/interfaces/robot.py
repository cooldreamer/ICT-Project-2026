"""Replaceable robot head/camera control interface (console and HTTP adapters)."""
from __future__ import annotations
import json
import logging
import time
from urllib.request import Request, urlopen


class RobotMovementInterface:
    """Contract for robot-facing attention and camera-orientation commands."""

    def orient_camera(self, azimuth_degrees: float, attention_score: float, reason: str = "addressed_speech") -> None:
        """Orient the robot's camera or head toward an estimated azimuth.

        Parameters:
            * azimuth_degrees : Target direction, where 0° is forward.
            * attention_score : Confidence that the speech addresses the robot.
            * reason : Explanation for the orientation command.

        Returns:
            None.

        Raises:
            NotImplementedError: This interface method must be implemented by
                a concrete robot adapter.
        """
        raise NotImplementedError

    def set_alertness(self, state: str, detail: str = "") -> None:
        """Report a high-level alertness state to the robot.

        Parameters:
            * state : Alertness state name.
            * detail : Optional context for the state change.

        Returns:
            None.

        Raises:
            NotImplementedError: This interface method must be implemented by
                a concrete robot adapter.
        """
        raise NotImplementedError


class ConsoleRobotInterface(RobotMovementInterface):
    """Safe default: logs intended motions but never moves physical hardware."""

    def orient_camera(self, azimuth_degrees: float, attention_score: float, reason: str = "addressed_speech") -> None:
        """Log a simulated camera-orientation command.

        Parameters:
            * azimuth_degrees : Target direction, where 0° is forward.
            * attention_score : Confidence that the speech addresses the robot.
            * reason : Explanation for the orientation command.

        Returns:
            None.
        """
        logging.info(
            "[SIMULATED ROBOT] orient camera/head to %+.1f° (confidence %.2f; %s)",
            azimuth_degrees, attention_score, reason,
        )

    def set_alertness(self, state: str, detail: str = "") -> None:
        """Log a simulated alertness update.

        Parameters:
            * state : Alertness state name.
            * detail : Optional context for the state change.

        Returns:
            None.
        """
        logging.info("[ROBOT ALERTNESS] %s %s", state, detail)


class HttpRobotInterface(RobotMovementInterface):
    """POST generic JSON commands to a robot gateway; adapt the schema to your robot."""

    def __init__(self, endpoint: str, timeout_seconds: float = 1.5) -> None:
        """Configure the gateway URL and request timeout.

        Parameters:
            * endpoint : Robot gateway URL accepting JSON POST commands.
            * timeout_seconds : Maximum time to wait for each HTTP request.

        Returns:
            None.
        """
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def _post(self, payload: dict) -> None:
        """POST one JSON command payload to the configured robot gateway.

        Parameters:
            * payload : JSON-serializable command dictionary.

        Notes:
            HTTP errors and other request failures are logged and suppressed.
            An HTTP error response is first represented internally as a
            ``RuntimeError``.

        Returns:
            None.
        """
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
        """Send a camera-orientation command with its direction and reason.

        Parameters:
            * azimuth_degrees : Target direction, where 0° is forward.
            * attention_score : Confidence that the speech addresses the robot.
            * reason : Explanation for the orientation command.

        Returns:
            None.
        """
        self._post({
            "command": "orient_camera",
            "azimuth_degrees": float(azimuth_degrees),
            "attention_score": float(attention_score),
            "reason": reason,
            "timestamp_unix": time.time(),
        })

    def set_alertness(self, state: str, detail: str = "") -> None:
        """Send an alertness-state command to the robot gateway.

        Parameters:
            * state : Alertness state name.
            * detail : Optional context for the state change.

        Returns:
            None.
        """
        self._post({"command": "set_alertness", "state": state, "detail": detail, "timestamp_unix": time.time()})
