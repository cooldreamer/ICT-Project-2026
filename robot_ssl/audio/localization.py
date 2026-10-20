"""SRP-PHAT-style far-field azimuth estimation for synchronised microphone arrays."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class LocalizationResult:
    azimuth_degrees: float
    confidence: float
    scores: np.ndarray


class SRPPHATLocalizer:
    """Estimate horizontal direction of arrival using phase-normalised cross spectra.

    Coordinate convention: x is robot-forward, y is robot-left; 0 degrees is
    straight ahead and positive angles rotate left. Microphones must share a clock.
    A non-collinear array with at least 3 microphones is recommended to reduce
    ambiguities. This is a far-field azimuth estimator, not a 3-D range estimator.
    """

    def __init__(
        self,
        microphone_positions_m: tuple[tuple[float, float], ...],
        sample_rate: int = 16_000,
        speed_of_sound_m_s: float = 343.0,
        angle_step_degrees: float = 2.0,
        min_frequency_hz: float = 250.0,
        max_frequency_hz: float = 7_000.0,
    ) -> None:
        self.positions = np.asarray(microphone_positions_m, dtype=np.float64)
        self.sample_rate = sample_rate
        self.speed_of_sound = speed_of_sound_m_s
        self.angles = np.arange(-180.0, 180.0, angle_step_degrees, dtype=np.float64)
        self.min_frequency_hz = min_frequency_hz
        self.max_frequency_hz = max_frequency_hz
        self._pair_indices = [
            (i, j)
            for i in range(len(self.positions))
            for j in range(i + 1, len(self.positions))
        ]

    def localize(self, frame: np.ndarray) -> LocalizationResult | None:
        data = np.asarray(frame, dtype=np.float64)
        if data.ndim != 2 or data.shape[1] != len(self.positions) or data.shape[0] < 128:
            return None
        if len(self.positions) < 2:
            return None
        centered = data - np.mean(data, axis=0, keepdims=True)
        energy = float(np.mean(centered * centered))
        if energy < 1e-7:
            return None

        window = np.hanning(data.shape[0])[:, None]
        spectra = np.fft.rfft(centered * window, axis=0)
        frequencies = np.fft.rfftfreq(data.shape[0], d=1.0 / self.sample_rate)
        band = (frequencies >= self.min_frequency_hz) & (frequencies <= min(self.max_frequency_hz, self.sample_rate / 2 - 1))
        if not np.any(band):
            return None
        omega = 2.0 * np.pi * frequencies[band]
        unit_vectors = np.column_stack((np.cos(np.deg2rad(self.angles)), np.sin(np.deg2rad(self.angles))))
        total_scores = np.zeros(len(self.angles), dtype=np.float64)
        pair_count = 0

        for i, j in self._pair_indices:
            cross = spectra[:, i] * np.conjugate(spectra[:, j])
            selected = cross[band]
            magnitude = np.abs(selected)
            valid = magnitude > 1e-12
            if np.count_nonzero(valid) < 8:
                continue
            phat = np.zeros_like(selected)
            phat[valid] = selected[valid] / magnitude[valid]
            # For x_i * conj(x_j), expected phase is exp(-j*w*tau), where
            # tau = arrival_time_i - arrival_time_j = -(p_i - p_j) dot u / c.
            delta_position = self.positions[i] - self.positions[j]
            delays = -(unit_vectors @ delta_position) / self.speed_of_sound
            steering = np.exp(1j * delays[:, None] * omega[None, :])
            total_scores += np.real(steering @ phat)
            pair_count += 1

        if pair_count == 0:
            return None
        total_scores /= (pair_count * np.count_nonzero(band))
        best_index = int(np.argmax(total_scores))
        baseline = float(np.mean(total_scores))
        peak = float(total_scores[best_index])
        confidence = float(np.clip((peak - baseline) / max(abs(peak), 1e-6), 0.0, 1.0))
        return LocalizationResult(
            azimuth_degrees=float(self.angles[best_index]),
            confidence=confidence,
            scores=total_scores,
        )
