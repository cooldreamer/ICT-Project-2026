"""Small runtime health/performance counter service."""
from __future__ import annotations
import time
from collections import deque


class HealthMonitor:
    """Track recent audio throughput and cumulative runtime health counters."""

    def __init__(self, window_seconds: float = 10.0) -> None:
        """Initialize the rolling frame-rate window and runtime counters.

        Parameters:
            * window_seconds : Time span used to calculate recent frame rate.

        Returns:
            None.
        """
        self.window_seconds = window_seconds
        self.frame_times: deque[float] = deque()
        self.audio_overflows = 0
        self.audio_errors = 0
        self.dropped_segments = 0
        self.started_at = time.monotonic()

    def record_frame(self, now: float | None = None) -> None:
        """Record a processed frame and discard timestamps outside the window.

        Parameters:
            * now : Optional monotonic timestamp; defaults to the current time.

        Returns:
            None.
        """
        now = time.monotonic() if now is None else now
        self.frame_times.append(now)
        cutoff = now - self.window_seconds
        while self.frame_times and self.frame_times[0] < cutoff:
            self.frame_times.popleft()

    def snapshot(self) -> dict:
        """Create a snapshot of current performance and health metrics.

        Returns:
            A dictionary containing frame rate, error counters, and uptime.
        """
        if len(self.frame_times) >= 2:
            duration = max(self.frame_times[-1] - self.frame_times[0], 1e-6)
            fps = (len(self.frame_times) - 1) / duration
        else:
            fps = 0.0
        return {
            "frames_per_second": round(fps, 1),
            "audio_overflows": self.audio_overflows,
            "audio_errors": self.audio_errors,
            "dropped_segments": self.dropped_segments,
            "uptime_seconds": round(time.monotonic() - self.started_at, 1),
        }
