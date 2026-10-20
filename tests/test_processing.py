import numpy as np
from robot_ssl.audio.processing import AudioCleaner, SpeechSegmenter, extract_frame_features


def test_cleaner_returns_finite_multichannel_audio():
    cleaner = AudioCleaner(sample_rate=16000, channels=2)
    frame = np.random.default_rng(2).normal(0, 0.03, (1280, 2)).astype(np.float32)
    cleaned = cleaner.clean(frame)
    assert cleaned.shape == frame.shape
    assert np.isfinite(cleaned).all()


def test_segmenter_returns_an_utterance_after_silence():
    sample_rate = 16000
    frame_samples = 1280
    segmenter = SpeechSegmenter(sample_rate, frame_samples, min_rms=0.004, end_silence_seconds=0.16, min_speech_seconds=0.16)
    quiet = np.zeros((frame_samples, 2), dtype=np.float32)
    speech = np.ones((frame_samples, 2), dtype=np.float32) * 0.05
    found = None
    now = 0.0
    for frame in [quiet] * 3 + [speech] * 6 + [quiet] * 4:
        now += frame_samples / sample_rate
        feat = extract_frame_features(frame, sample_rate)
        found = segmenter.process(frame, feat.rms, 30.0 if np.any(frame) else None, False, doa_confidence=0.7, now=now) or found
    assert found is not None
    assert found.samples.ndim == 2
    assert found.samples.shape[1] == 2
    assert found.doa_angles_degrees
