"""Tests for application-level audio routing."""

import numpy as np

from robot_ssl.app import RobotAudioApp
from robot_ssl.config import AppConfig


def test_split_audio_data_routes_xvf3800_channels():
    """Check that the configured XVF3800 channels are separated correctly.

    Returns:
        None.
    """
    app = object.__new__(RobotAudioApp)
    app.config = AppConfig()
    frame = np.arange(24, dtype=np.float32).reshape(4, 6)

    asr, summed, microphones = app._splitAudioData(frame)

    np.testing.assert_array_equal(asr, frame[:, 0])
    np.testing.assert_array_equal(summed, frame[:, 1])
    np.testing.assert_array_equal(microphones, frame[:, 2:6])
