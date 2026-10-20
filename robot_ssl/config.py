"""Configuration for the robot audio perception pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

# Robot-relative microphone coordinates in metres: (forward, left).
# This default is a square 10 cm array. Replace it with measured coordinates for
# the actual microphone array, in the same order as the input channels.
DEFAULT_MIC_POSITIONS: Tuple[Tuple[float, float], ...] = (
    (0.05, 0.05),
    (0.05, -0.05),
    (-0.05, -0.05),
    (-0.05, 0.05),
)


@dataclass
class AppConfig:
    sample_rate: int = 16_000
    channels: int = 4
    frame_samples: int = 1_280  # 80 ms at 16 kHz; matches openWakeWord frame sizing
    microphone_positions_m: Tuple[Tuple[float, float], ...] = DEFAULT_MIC_POSITIONS
    speed_of_sound_m_s: float = 343.0
    
    doa_step_degrees: float = 2.0
    vad_min_rms: float = 0.004
    vad_noise_multiplier: float = 3.0
    vad_end_silence_seconds: float = 0.55
    vad_pre_roll_seconds: float = 0.24
    vad_min_speech_seconds: float = 0.24
    vad_max_segment_seconds: float = 12.0
    
    wakeword_threshold: float = 0.50
    wakeword_cooldown_seconds: float = 2.0
    session_timeout_seconds: float = 8.0
    subject_angle_tolerance_degrees: float = 35.0
    
    stt_model: str = "base"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    wakeword_model_path: str | None = None
    accent_model_path: str | None = None
    
    robot_endpoint: str | None = None
    server_endpoint: str | None = None
    database_path: Path = Path("data/robot_audio.sqlite3")
    
    log_level: str = "INFO"
    
    robot_hostname = "192.168.1.8"
    console_hostname = "192.168.1.210"
    discovery_server_port = 11811
    discovery_server_host = robot_hostname
    ros_domain_id = "9"
    
    def validate(self) -> None:
        if self.sample_rate != 16_000:
            raise ValueError(
                "This implementation currently expects 16 kHz audio (openWakeWord input format)."
            )
        if self.frame_samples <= 0:
            raise ValueError("frame_samples must be a positive integer")
        if self.channels < 1:
            raise ValueError("channels must be at least 1")
        if self.channels != len(self.microphone_positions_m):
            raise ValueError(
                f"Configured {self.channels} input channels but have "
                f"{len(self.microphone_positions_m)} microphone positions. "
                "Set --channels and/or supply --mic-geometry to match the device."
            )
        if self.doa_step_degrees <= 0:
            raise ValueError("doa_step_degrees must be positive")
