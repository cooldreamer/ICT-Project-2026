"""Speech acoustic-feature extraction and an optional trained accent classifier."""
from __future__ import annotations

from pathlib import Path
import numpy as np
from scipy.signal import find_peaks

from robot_ssl.models import VoiceTraits


def _estimate_pitch_median(audio: np.ndarray, sample_rate: int) -> float | None:
    """Lightweight autocorrelation pitch estimate; unreliable for noisy/unvoiced audio."""
    signal = np.asarray(audio, dtype=np.float64)
    frame_size = int(0.040 * sample_rate)
    hop = int(0.020 * sample_rate)
    if signal.size < frame_size:
        return None
    values: list[float] = []
    min_lag = max(1, int(sample_rate / 350.0))
    max_lag = max(min_lag + 1, int(sample_rate / 70.0))
    for start in range(0, len(signal) - frame_size + 1, hop):
        frame = signal[start:start + frame_size].copy()
        frame -= frame.mean()
        peak = np.max(np.abs(frame))
        if peak < 0.01:
            continue
        frame *= np.hanning(len(frame))
        autocorr = np.correlate(frame, frame, mode="full")[len(frame) - 1:]
        if autocorr[0] <= 1e-10:
            continue
        autocorr /= autocorr[0]
        region = autocorr[min_lag:max_lag + 1]
        if region.size == 0:
            continue
        peaks, _ = find_peaks(region)
        if peaks.size == 0:
            continue
        lag = int(peaks[np.argmax(region[peaks])]) + min_lag
        if autocorr[lag] >= 0.25:
            values.append(sample_rate / lag)
    return float(np.median(values)) if values else None


def extract_voice_traits(audio: np.ndarray, sample_rate: int = 16_000) -> VoiceTraits:
    signal = np.asarray(audio, dtype=np.float32).reshape(-1)
    if signal.size == 0:
        return VoiceTraits()
    rms = float(np.sqrt(np.mean(np.square(signal, dtype=np.float64)) + 1e-12))
    centered = signal - float(signal.mean())
    spectrum = np.abs(np.fft.rfft(centered * np.hanning(len(centered))))
    freqs = np.fft.rfftfreq(len(centered), d=1.0 / sample_rate)
    total = float(spectrum.sum())
    centroid = float(np.dot(freqs, spectrum) / total) if total > 1e-12 else None
    cumulative = np.cumsum(spectrum)
    rolloff = None
    if total > 1e-12:
        roll_index = min(int(np.searchsorted(cumulative, 0.85 * total)), len(freqs) - 1)
        rolloff = float(freqs[roll_index])
    zcr = float(np.mean(np.signbit(centered[1:]) != np.signbit(centered[:-1]))) if len(centered) > 1 else 0.0
    return VoiceTraits(
        pitch_median_hz=_estimate_pitch_median(signal, sample_rate),
        rms_dbfs=20.0 * float(np.log10(max(rms, 1e-6))),
        spectral_centroid_hz=centroid,
        spectral_rolloff_hz=rolloff,
        zero_crossing_rate=zcr,
    )


class AccentClassifier:
    """Adapter for an externally trained scikit-learn-compatible accent model.

    The project deliberately ships without an accent model: a few handcrafted
    spectral statistics cannot reliably identify a person's accent. A supplied
    model must have been trained and validated on consented, representative data.
    It should accept [pitch, RMS dBFS, centroid, rolloff, ZCR] in that order.
    """

    def __init__(self, model_path: str | None = None) -> None:
        self.model = None
        if model_path:
            try:
                import joblib  # optional dependency
            except ImportError as exc:
                raise RuntimeError("Install joblib to load --accent-model") from exc
            self.model = joblib.load(Path(model_path))

    def predict(self, traits: VoiceTraits) -> tuple[str, float | None]:
        if self.model is None:
            return "unknown (no trained accent classifier configured)", None
        vector = np.array([[
            traits.pitch_median_hz or 0.0,
            traits.rms_dbfs or -120.0,
            traits.spectral_centroid_hz or 0.0,
            traits.spectral_rolloff_hz or 0.0,
            traits.zero_crossing_rate or 0.0,
        ]], dtype=np.float32)
        label = str(self.model.predict(vector)[0])
        confidence: float | None = None
        if hasattr(self.model, "predict_proba"):
            probabilities = np.asarray(self.model.predict_proba(vector))[0]
            if probabilities.size:
                confidence = float(np.max(probabilities))
        return label, confidence
