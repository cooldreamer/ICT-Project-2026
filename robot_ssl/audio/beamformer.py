"""Frequency-domain delay-and-sum beamformer steered by the estimated azimuth."""
from __future__ import annotations

import numpy as np


class DelayAndSumBeamformer:
    """Steer multichannel audio toward an azimuth and average aligned channels."""

    def __init__(
        self,
        microphone_positions_m: tuple[tuple[float, float], ...],
        sample_rate: int = 16_000,
        speed_of_sound_m_s: float = 343.0,
    ) -> None:
        """Initialize the beamformer with microphone geometry and audio parameters.

        Parameters:
            * microphone_positions_m : Microphone coordinates in metres, ordered
                to match the input audio channels.
            * sample_rate : Audio sample rate in hertz.
            * speed_of_sound_m_s : Assumed speed of sound in metres per second.

        Returns:
            None.
        """
        self.positions = np.asarray(microphone_positions_m, dtype=np.float64)
        self.sample_rate = sample_rate
        self.speed_of_sound = speed_of_sound_m_s

    def beamform(self, samples: np.ndarray, azimuth_degrees: float | None) -> np.ndarray:
        """Create mono audio steered to the requested azimuth when available.

        Parameters:
            * samples : Audio samples as a mono array or a
                ``(sample_count, channel_count)`` multichannel array.
            * azimuth_degrees : Estimated source direction in degrees, with 0°
                forward and positive angles to the left; ``None`` uses channel
                averaging without steering.

        Returns:
            A one-dimensional float32 audio signal.

        Raises:
            ValueError: If the audio channel count does not match the microphone
                geometry.
        """
        data = np.asarray(samples, dtype=np.float32)
        if data.ndim == 1:
            return data.copy()
        if data.shape[1] == 1 or azimuth_degrees is None:
            return data.mean(axis=1).astype(np.float32)
        if data.shape[1] != len(self.positions):
            raise ValueError("Audio channel count does not match microphone geometry")

        theta = np.deg2rad(azimuth_degrees)
        direction = np.array([np.cos(theta), np.sin(theta)])
        arrival_delays = -(self.positions @ direction) / self.speed_of_sound

        # Padding limits circular-wrap artefacts when using FFT phase shifts.
        pad_samples = max(32, round(0.04 * self.sample_rate))
        padded = np.pad(data, ((pad_samples, pad_samples), (0, 0)))
        n_fft = 1 << (padded.shape[0] - 1).bit_length()
        frequencies = np.fft.rfftfreq(n_fft, d=1.0 / self.sample_rate)
        spectrum = np.fft.rfft(padded, n=n_fft, axis=0)
        for channel, delay in enumerate(arrival_delays):
            # The captured channel has phase exp(-j*w*delay); invert that phase
            # so the target direction adds coherently across microphones.
            spectrum[:, channel] *= np.exp(1j * 2.0 * np.pi * frequencies * delay)
        aligned = np.fft.irfft(spectrum, n=n_fft, axis=0)
        output = aligned[pad_samples:pad_samples + data.shape[0], :].mean(axis=1)
        return output.astype(np.float32)
