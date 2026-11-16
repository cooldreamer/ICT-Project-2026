"""Tests for command-line demo functionality."""

from main import run_doa_demo
from robot_ssl.config import DEFAULT_MIC_POSITIONS


def test_doa_demo_localizes_synthetic_source():
    """Check that the synthetic DoA demo succeeds with default geometry.

    Returns:
        None.
    """
    assert run_doa_demo(DEFAULT_MIC_POSITIONS) == 0


def test_doa_demo_rejects_fewer_than_two_microphones():
    """Check that the DoA demo reports insufficient microphone geometry.

    Returns:
        None.
    """
    assert run_doa_demo(((0.0, 0.0),)) == 2
