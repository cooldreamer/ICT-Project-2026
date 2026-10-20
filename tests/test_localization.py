import numpy as np

from robot_ssl.audio.localization import SRPPHATLocalizer
from robot_ssl.app import circular_mean_degrees
from robot_ssl.config import DEFAULT_MIC_POSITIONS


def synthesize_far_field(angle_degrees: float, n_samples: int = 8192, sample_rate: int = 16000):
    rng = np.random.default_rng(11)
    source = rng.normal(0.0, 0.1, n_samples)
    source_spectrum = np.fft.rfft(source)
    frequencies = np.fft.rfftfreq(n_samples, 1.0 / sample_rate)
    theta = np.deg2rad(angle_degrees)
    direction = np.array([np.cos(theta), np.sin(theta)])
    channels = []
    for position in np.asarray(DEFAULT_MIC_POSITIONS):
        delay = -float(np.dot(position, direction)) / 343.0
        channels.append(np.fft.irfft(source_spectrum * np.exp(-1j * 2 * np.pi * frequencies * delay), n=n_samples))
    return np.column_stack(channels).astype(np.float32)


def test_srp_phat_estimates_positive_left_azimuth():
    audio = synthesize_far_field(40.0)
    result = SRPPHATLocalizer(DEFAULT_MIC_POSITIONS, angle_step_degrees=1.0).localize(audio)
    assert result is not None
    assert abs((result.azimuth_degrees - 40.0 + 180.0) % 360.0 - 180.0) <= 5.0


def test_circular_mean_works_across_angle_wrap():
    result = circular_mean_degrees([179.0, -179.0])
    assert result is not None
    assert abs(abs(result) - 180.0) < 2.0
