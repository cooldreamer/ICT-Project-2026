"""Audio cleaning, lightweight feature extraction, and speech segmentation."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time
import numpy as np
from scipy.signal import butter, sosfilt

from robot_ssl.models import AudioSegment


@dataclass
class FrameFeatures:
    rms: float
    rms_dbfs: float
    zero_crossing_rate: float
    spectral_centroid_hz: float
    clipped_fraction: float


class AudioCleaner:
    """Remove DC/low-frequency rumble and constrain the band for speech processing."""

    def __init__(self, sample_rate: int, channels: int) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        upper_hz = min(7_500.0, sample_rate * 0.45)
        self.sos = butter(4, [80.0, upper_hz], btype="bandpass", fs=sample_rate, output="sos")
        self.zi = np.zeros((self.sos.shape[0], 2, channels), dtype=np.float64)

    def clean(self, frame: np.ndarray) -> np.ndarray:
        data = np.asarray(frame, dtype=np.float32)
        if data.ndim == 1:
            data = data[:, None]
        if data.shape[1] != self.channels:
            raise ValueError(f"Expected {self.channels} channels, received {data.shape[1]}")
        data = np.nan_to_num(data, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        data = np.clip(data, -1.0, 1.0)
        filtered, self.zi = sosfilt(self.sos, data, axis=0, zi=self.zi)
        return np.asarray(filtered, dtype=np.float32)


def extract_frame_features(frame: np.ndarray, sample_rate: int) -> FrameFeatures:
    """Extract inexpensive descriptive features from a mono or multichannel frame."""
    data = np.asarray(frame, dtype=np.float32)
    mono = data if data.ndim == 1 else data.mean(axis=1)
    if mono.size == 0:
        return FrameFeatures(0.0, -120.0, 0.0, 0.0, 0.0)
    # Use all channels for loudness so phase cancellation in a naïve mono mix
    # does not suppress VAD when the array mics have different arrival times.
    rms = float(np.sqrt(np.mean(np.square(data, dtype=np.float64)) + 1e-12))
    centered = mono - float(np.mean(mono))
    zcr = float(np.mean(np.signbit(centered[1:]) != np.signbit(centered[:-1]))) if mono.size > 1 else 0.0
    spectrum = np.abs(np.fft.rfft(centered * np.hanning(len(centered))))
    frequencies = np.fft.rfftfreq(len(centered), d=1.0 / sample_rate)
    mag_sum = float(spectrum.sum())
    centroid = float(np.dot(frequencies, spectrum) / mag_sum) if mag_sum > 1e-12 else 0.0
    clipped = float(np.mean(np.abs(data) >= 0.999))
    return FrameFeatures(
        rms=rms,
        rms_dbfs=20.0 * float(np.log10(max(rms, 1e-6))),
        zero_crossing_rate=zcr,
        spectral_centroid_hz=centroid,
        clipped_fraction=clipped,
    )


class SpeechSegmenter:
    """Energy-based VAD with adaptive floor, pre-roll, and silence-based endpointing.

    This is intentionally a simple baseline. For noisy/moving robots, replace or
    augment it with WebRTC VAD, Silero VAD, or a trained speech-activity model.
    """

    def __init__(
        self,
        sample_rate: int,
        frame_samples: int,
        min_rms: float = 0.004,
        noise_multiplier: float = 3.0,
        end_silence_seconds: float = 0.55,
        pre_roll_seconds: float = 0.24,
        min_speech_seconds: float = 0.24,
        max_segment_seconds: float = 12.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self.min_rms = min_rms
        self.noise_multiplier = noise_multiplier
        self.end_silence_frames = max(1, round(end_silence_seconds * sample_rate / frame_samples))
        self.pre_roll_frames = max(1, round(pre_roll_seconds * sample_rate / frame_samples))
        self.min_speech_frames = max(1, round(min_speech_seconds * sample_rate / frame_samples))
        self.max_segment_frames = max(self.min_speech_frames, round(max_segment_seconds * sample_rate / frame_samples))
        self.noise_rms = 0.002
        self.pre_roll: deque[tuple[np.ndarray, float | None, float | None, bool, float]] = deque(maxlen=self.pre_roll_frames)
        self.active = False
        self.frames: list[np.ndarray] = []
        self.angles: list[float] = []
        self.wakeword_seen = False
        self.doa_confidences: list[float] = []
        self.silence_frames = 0
        self.speech_frames = 0
        self.segment_start = 0.0

    def process(
        self,
        frame: np.ndarray,
        rms: float,
        doa_angle: float | None,
        wakeword_detected: bool,
        doa_confidence: float | None = None,
        now: float | None = None,
    ) -> AudioSegment | None:
        now = time.monotonic() if now is None else now
        speech_threshold = max(self.min_rms, self.noise_rms * self.noise_multiplier)
        is_speech = rms >= speech_threshold

        # Update the noise floor only when the frame appears non-speech.
        if not is_speech:
            self.noise_rms = 0.97 * self.noise_rms + 0.03 * min(rms, self.min_rms)

        if not self.active and is_speech:
            self.active = True
            self.frames = [entry[0] for entry in self.pre_roll]
            self.angles = [entry[1] for entry in self.pre_roll if entry[1] is not None]
            self.doa_confidences = [entry[2] for entry in self.pre_roll if entry[2] is not None]
            self.wakeword_seen = any(entry[3] for entry in self.pre_roll) or wakeword_detected
            self.segment_start = self.pre_roll[0][4] if self.pre_roll else now
            self.silence_frames = 0
            self.speech_frames = 1
        elif self.active:
            self.speech_frames += int(is_speech)
            self.wakeword_seen = self.wakeword_seen or wakeword_detected
            if is_speech:
                self.silence_frames = 0
            else:
                self.silence_frames += 1

        if self.active:
            self.frames.append(np.array(frame, dtype=np.float32, copy=True))
            if doa_angle is not None and is_speech:
                self.angles.append(float(doa_angle))
                if doa_confidence is not None:
                    self.doa_confidences.append(float(doa_confidence))

            should_end = (
                self.silence_frames >= self.end_silence_frames
                or len(self.frames) >= self.max_segment_frames
            )
            if should_end:
                segment = None
                if self.speech_frames >= self.min_speech_frames and self.frames:
                    segment = AudioSegment(
                        samples=np.concatenate(self.frames, axis=0).astype(np.float32, copy=False),
                        doa_angles_degrees=self.angles.copy(),
                        doa_confidences=self.doa_confidences.copy(),
                        wakeword_detected=self.wakeword_seen,
                        start_monotonic=self.segment_start,
                        end_monotonic=now,
                    )
                self.active = False
                self.frames = []
                self.angles = []
                self.doa_confidences = []
                self.wakeword_seen = False
                self.silence_frames = 0
                self.speech_frames = 0
                self.pre_roll.clear()
                return segment
        else:
            self.pre_roll.append((np.array(frame, dtype=np.float32, copy=True), doa_angle, doa_confidence, wakeword_detected, now))
        return None
