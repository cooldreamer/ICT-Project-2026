"""Optional openWakeWord integration with a safe disabled fallback."""
from __future__ import annotations
import logging
import time
import numpy as np


class WakeWordDetector:
    def __init__(self, model_path: str | None, threshold: float = 0.5, cooldown_seconds: float = 2.0) -> None:
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.last_trigger = 0.0
        self.model = None
        self.model_name: str | None = None
        if model_path:
            try:
                from openwakeword.model import Model
            except ImportError as exc:
                raise RuntimeError(
                    "A wake-word model path was supplied. Install the optional dependency with: pip install openwakeword"
                ) from exc
            self.model = Model(wakeword_models=[model_path], inference_framework="onnx" if model_path.lower().endswith(".onnx") else "tflite")
            self.model_name = model_path
            logging.info("Loaded wake-word model: %s", model_path)

    @property
    def enabled(self) -> bool:
        return self.model is not None

    def detect(self, mono_audio: np.ndarray) -> tuple[bool, float]:
        """Consume one mono float frame and return (triggered, best model score)."""
        if self.model is None:
            return False, 0.0
        mono = np.asarray(mono_audio, dtype=np.float32).reshape(-1)
        pcm = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
        # openWakeWord accepts 16 kHz, 16-bit PCM frames; buffering here means
        # callers may use a frame size other than the model's usual 80 ms.
        if not hasattr(self, "_pending"):
            self._pending = np.empty(0, dtype=np.int16)
        self._pending = np.concatenate((self._pending, pcm))
        event = False
        best_score = 0.0
        chunk_samples = 1280
        while self._pending.size >= chunk_samples:
            chunk = self._pending[:chunk_samples]
            self._pending = self._pending[chunk_samples:]
            scores = self.model.predict(chunk)
            score = max((float(v) for v in scores.values()), default=0.0)
            best_score = max(best_score, score)
            now = time.monotonic()
            if score >= self.threshold and now - self.last_trigger >= self.cooldown_seconds:
                event = True
                self.last_trigger = now
        return event, best_score
