"""Lazy wrapper around faster-whisper; no network/server is needed during inference after model setup."""
from __future__ import annotations
import logging
import numpy as np


class SpeechToText:
    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8") -> None:
        self.model = None
        self.error: str | None = None
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
            logging.info("Loaded faster-whisper model '%s' on %s", model_size, device)
        except Exception as exc:  # optional backend/model download/runtime failure
            self.error = f"STT unavailable: {exc}"
            logging.warning(self.error)

    @property
    def available(self) -> bool:
        return self.model is not None

    def transcribe(self, audio: np.ndarray) -> tuple[str, str | None]:
        if self.model is None:
            return "", None
        signal = np.asarray(audio, dtype=np.float32).reshape(-1)
        if signal.size < 2_000:
            return "", None
        segments, info = self.model.transcribe(
            signal,
            language=None,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=3,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, getattr(info, "language", None)
