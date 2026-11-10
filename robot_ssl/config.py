"""Module managing configuration settings for the whole project.
Includes definitions for default/XVF3800-specific values and the managing AppConfig class."""

from dataclasses import dataclass # for templating of the configuration module into an attribute-centred class
from pathlib import Path # for storing the path to the sqlite database
from typing import Tuple # for type declaration of variables as a Tuple
import warnings # for raising warnings for less critical issues in the project's operation
import json # for loading and reading a json file into a dictionary

# Robot-relative microphone coordinates in metres: (forward, left).
# This default is a square 10 cm array. Replace it with measured coordinates for
# the actual microphone array, in the same order as its mapped microphone channels.
DEFAULT_MIC_POSITIONS: Tuple[Tuple[float, float], ...] = (
    (0.05, 0.05),
    (0.05, -0.05),
    (-0.05, -0.05),
    (-0.05, 0.05),
)

# Default settings correct for the XVF3800 mic array.  Otherwise like DEFAULT_MIC_POSITIONS.
XVF3800_MIC_POSITIONS: Tuple[Tuple[float, float], ...] = (
    (0.05, 0.05),
    (0.05, -0.05),
    (-0.05, -0.05),
    (-0.05, 0.05),
)

XVF3800_INPUT_CHANNELS = 6
XVF3800_SAMPLE_RATE = 16_000
XVF3800_MIC_CHANNEL_INDICES: Tuple[int, ...] = (2, 3, 4, 5) # indexed from 0

@dataclass
class AppConfig:
    """Class managing the configuration settings for the whole project.

    Device-specific values come from module constants when the XVF3800 profile
    is enabled. Otherwise, underscored fields provide the defaults. Settings
    from ``robot_ssl/config.json`` are applied after construction and override
    constructor-provided values with matching names. Device-dependent
    properties are installed dynamically during initialization.

    Microphone coordinates are example values and must be replaced with
    measurements for the physical array. Non-16-kHz audio is not resampled;
    wake-word inference expects 16 kHz.
    """

    use_xvf3800_mic_model: bool = True # overrides other settings if True
    
    # these properties are ignored if use_xvf3800_mic_model is True
    _sample_rate: int = 16_000
    _input_channels: int = 4
    _microphone_positions_m: Tuple[Tuple[float, float], ...] = DEFAULT_MIC_POSITIONS
    _microphone_channel_indices: Tuple[int, ...] = (0, 1, 2, 3)
    
    property_connections = {"input_channels": "XVF3800_INPUT_CHANNELS", "sample_rate": "XVF3800_SAMPLE_RATE", "microphone_positions_m": "XVF3800_MIC_POSITIONS", "microphone_channel_indices": "XVF3800_MIC_CHANNEL_INDICES"}
    
    speed_of_sound_m_s: float = 340.0
    
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
    
    # This one we'll have to set manually
    # @property
    # def channels(self):
    #     # Compatibility alias for the number of geometry microphone channels.
    #     return len(self.microphone_positions_m)
    
    # @property
    # # @swap_with_xvf3800_check(attributename="_sample_rate")
    # def sample_rate(self):
    #     return 16_000 if self.use_xvf3800_mic_model else self._sample_rate
    
    # @property
    # # @swap_with_xvf3800_check(attributename="_microphone_positions_m")
    # def microphone_positions_m(self):
    #     return XVF3800_MIC_POSITIONS if self.use_xvf3800_mic_model else self._microphone_positions_m

    # @property
    # # # @swap_with_xvf3800_check(attributename="_microphone_channel_indices")
    # def microphone_channel_indices(self):
    #     return XVF3800_MIC_CHANNEL_INDICES if self.use_xvf3800_mic_model else self._microphone_channel_indices
    
    # property variables, to make interpreter shut up.  These values are all replaced immediately (in __post_init__)
    sample_rate = 0
    input_channels = 0
    microphone_positions_m = ()
    microphone_channel_indices = ()
    
    channels = 0
    
    def __post_init__(self):
        """Install device-dependent properties and apply JSON overrides.

        Returns:
            None.
        """
        self.load_properties() # interpreter hates this but it works
        self.channels = property(lambda self: len(self.microphone_positions_m))
        
        json_settings = self.load_json()
        if json_settings:
            # Replace property JSON entries with attribute JSON entries, to preserve property behaviour correctly
            json_settings = dict([(f"_{key}" if key in self.property_connections else key, value) for key, value in json_settings.items()])
            
            # Load JSON settings into AppConfig attributes
            # (Note 1: the way this is loaded, the last entry to share the name of an attribute will be ultimately used)
            # (Note 2: since this is done in __post_init__, the JSON settings will override any values set in the constructor)
            dir_self = dir(self)
            for setting_name, setting_val in [(a,b) for a,b in json_settings.items() if a in dir_self]:
                setattr(self, setting_name, setting_val)
        
        return
        
    def load_json(self):
        """Load settings from ``robot_ssl/config.json`` if it exists.

        Returns:
            The settings dictionary, or an empty dictionary if the file is missing.
        """
        json_settings = {}
        try:
            with open("robot_ssl/config.json") as json_file:
                json_settings = json.load(json_file)
        except FileNotFoundError:
            print("JSON config file not found.  Using input or default settings.")
        
        return json_settings
    
    def load_properties(self):
        """Bind device-dependent settings to the active microphone profile.

        With the XVF3800 profile enabled, public settings read from module constants.
        Otherwise, they read from their underscored instance fields.

        Returns:
            None.
        """
        for setting_name, setting_val in [(a,b) for a,b in self.property_connections.items() if a in dir(self)]:
            setattr(self, setting_name, property(lambda self: globals()[setting_val] if self.use_xvf3800_mic_model else getattr(self, f"_{setting_name}")))
        return

    def validate(self) -> None:
        """Validate microphone and processing settings.

        Raises:
            ValueError: If the frame size, microphone/channel configuration,
                or DoA angular step is invalid.

        Warns:
            UserWarning: If the sample rate is not 16 kHz.

        Returns:
            None.
        """
        if self.sample_rate != 16_000:
            # To do: add a resampler to the pipeline so that openWakeWord can be used with other sample rates
            warnings.warn("openWakeWord expects 16 kHz audio.  If an openWakeWord model is being used, this will not work!", UserWarning)
        if self.frame_samples <= 0:
            raise ValueError("frame_samples must be a positive integer")
        
        if len(self.microphone_positions_m) < 1: # type: ignore
            raise ValueError("At least one input must be present")
        
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

if __name__ == "__main__":
    AppConfig()