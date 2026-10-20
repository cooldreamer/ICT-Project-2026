"""Wakeword session and continued-subject speech tracking."""
from __future__ import annotations
import math
import time
from robot_ssl.models import VoiceTraits


def circular_angle_difference(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


class SubjectSpeechDetectionModel:
    """Transparent baseline scorer, not a trained ML classifier.

    Replace this class with a validated speaker embedding / diarisation model
    if the robot must reliably distinguish people in multi-speaker environments.
    """
    def score(self, reference: VoiceTraits | None, current: VoiceTraits, angle_delta: float) -> float:
        spatial = math.exp(-angle_delta / 30.0)
        if reference is None:
            return 0.75 * spatial + 0.25 * 0.5

        similarities: list[float] = []
        if reference.pitch_median_hz and current.pitch_median_hz:
            pitch_delta = abs(reference.pitch_median_hz - current.pitch_median_hz) / max(reference.pitch_median_hz, 80.0)
            similarities.append(math.exp(-pitch_delta / 0.25))
        if reference.spectral_centroid_hz and current.spectral_centroid_hz:
            centroid_delta = abs(reference.spectral_centroid_hz - current.spectral_centroid_hz) / max(reference.spectral_centroid_hz, 500.0)
            similarities.append(math.exp(-centroid_delta / 0.45))
        if reference.zero_crossing_rate is not None and current.zero_crossing_rate is not None:
            similarities.append(math.exp(-abs(reference.zero_crossing_rate - current.zero_crossing_rate) / 0.08))
        voice_similarity = sum(similarities) / len(similarities) if similarities else 0.5
        return float(max(0.0, min(1.0, 0.55 * spatial + 0.45 * voice_similarity)))


class AttentionMaintenanceSystem:
    def __init__(self, timeout_seconds: float = 8.0, angle_tolerance_degrees: float = 35.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.angle_tolerance_degrees = angle_tolerance_degrees
        self.subject_angle: float | None = None
        self.subject_traits: VoiceTraits | None = None
        self.active_until = 0.0
        self.subject_model = SubjectSpeechDetectionModel()

    @property
    def active(self) -> bool:
        return time.monotonic() < self.active_until

    def engage(self, angle: float | None, traits: VoiceTraits, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if angle is not None:
            self.subject_angle = angle
        self.subject_traits = traits
        self.active_until = now + self.timeout_seconds

    def assess_continuation(
        self,
        angle: float | None,
        traits: VoiceTraits,
        speech_detected: bool = True,
        now: float | None = None,
    ) -> float:
        now = time.monotonic() if now is None else now
        if not speech_detected or now >= self.active_until or self.subject_angle is None or angle is None:
            return 0.0
        delta = circular_angle_difference(angle, self.subject_angle)
        if delta > self.angle_tolerance_degrees:
            return 0.0
        score = self.subject_model.score(self.subject_traits, traits, delta)
        if score >= 0.55:
            self.active_until = now + self.timeout_seconds
            # Smoothly follow moderate head/robot movement without jumping to other speakers.
            self.subject_angle = (0.8 * self.subject_angle + 0.2 * angle)
            self.subject_traits = traits
        return score
