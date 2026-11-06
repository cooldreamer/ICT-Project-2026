"""Configuration for the robot audio perception pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple
import warnings

# Robot-relative microphone coordinates in metres: (forward, left).
# This default is a square 10 cm array. Replace it with measured coordinates for
# the actual microphone array, in the same order as its mapped microphone channels.
DEFAULT_MIC_POSITIONS: Tuple[Tuple[float, float], ...] = (
    (0.05, 0.05),
    (0.05, -0.05),
    (-0.05, -0.05),
    (-0.05, 0.05),
)

XVF3800_MIC_POSITIONS: Tuple[Tuple[float, float], ...] = (
    (0.05, 0.05),
    (0.05, -0.05),
    (-0.05, -0.05),
    (-0.05, 0.05),
)

XVF3800_INPUT_CHANNELS = 6
XVF3800_MIC_CHANNEL_INDICES: Tuple[int, ...] = (2, 3, 4, 5) # indexed from 0

# to do: add config json file which is read in by python file
@dataclass
class AppConfig:
    use_xvf3800_mic_model: bool = True # overrides other settings if True
    
    # these properties are ignored if use_xvf3800_mic_model is True
    _sample_rate: int = 16_000
    _input_channels: int = 4
    _microphone_positions_m: Tuple[Tuple[float, float], ...] = DEFAULT_MIC_POSITIONS
    _microphone_channel_indices: Tuple[int, ...] = (0, 1, 2, 3)
    
    # speed of sound in Canberra at average elevation (570 m) and mean max temperature in November (23.5 C)
    # (this should be changed depending on your circumstances)
    speed_of_sound_m_s: float = 345.18
    
    
    doa_step_degrees: float = 2.0
    vad_min_rms: float = 0.004
    vad_noise_multiplier: float = 3.0
    vad_end_silence_seconds: float = 0.55
    vad_pre_roll_seconds: float = 0.24
    vad_min_speech_seconds: float = 0.24
    vad_max_segment_seconds: float = 12.0
    
    frame_samples: int = 1_280  # 80 ms at 16 kHz; matches openWakeWord frame sizing
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
    
    @property
    def channels(self):
        # Compatibility alias for the number of geometry microphone channels.
        return len(self.microphone_positions_m)

    @property
    def input_channels(self):
        return XVF3800_INPUT_CHANNELS if self.use_xvf3800_mic_model else self._input_channels
    
    @property
    def sample_rate(self):
        return 16_000 if self.use_xvf3800_mic_model else self._sample_rate
    
    @property
    def microphone_positions_m(self):
        return XVF3800_MIC_POSITIONS if self.use_xvf3800_mic_model else self._microphone_positions_m

    @property
    def microphone_channel_indices(self):
        return XVF3800_MIC_CHANNEL_INDICES if self.use_xvf3800_mic_model else self._microphone_channel_indices

    def validate(self) -> None:
        if self.sample_rate != 16_000:
            # To do: add a resampler to the pipeline so that openWakeWord can be used with other sample rates
            warnings.warn("openWakeWord expects 16 kHz audio.  If an openWakeWord model is being used, this will not work!", UserWarning)
        if self.frame_samples <= 0:
            raise ValueError("frame_samples must be a positive integer")
        
        if len(self.microphone_positions_m) < 1:
            raise ValueError("at least one input must be preset")
        
        if self.input_channels < 1:
            raise ValueError("input_channels must be at least 1")
        if len(self.microphone_channel_indices) != len(self.microphone_positions_m):
            raise ValueError("Each microphone position must have a corresponding input channel index")
        if len(set(self.microphone_channel_indices)) != len(self.microphone_channel_indices):
            raise ValueError("Each microphone can only be associated with one channel")
        if any(index < 0 or index >= self.input_channels for index in self.microphone_channel_indices):
            raise ValueError("Each microphone must have a valid corresponding input channel index")
        
        if self.doa_step_degrees <= 0:
            raise ValueError("doa_step_degrees must be positive")
