"""Shared data structures used between audio, attention, and robot modules."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import numpy as np


@dataclass
class VoiceTraits:
    """Acoustic descriptors; these are not a biometric identity or reliable accent label."""
    pitch_median_hz: float | None = None
    rms_dbfs: float | None = None
    spectral_centroid_hz: float | None = None
    spectral_rolloff_hz: float | None = None
    zero_crossing_rate: float | None = None
    language: str | None = None
    accent_guess: str = "unknown (no trained accent classifier configured)"
    accent_confidence: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AudioSegment:
    """One utterance segment retained as multichannel float32 audio."""
    samples: np.ndarray  # shape=(sample_count, channels), float32 in approximately [-1, 1]
    doa_angles_degrees: list[float]
    doa_confidences: list[float]
    wakeword_detected: bool
    start_monotonic: float
    end_monotonic: float

    @property
    def duration_seconds(self) -> float:
        return float(self.samples.shape[0]) / 16_000.0
