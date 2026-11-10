"""Lazy wrapper around faster-whisper; no network/server is needed during inference after model setup."""
from __future__ import annotations
import logging
import numpy as np


class SpeechToText:
    """Optional faster-whisper adapter for utterance transcription."""

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8") -> None:
        """Attempt to load a Whisper model with the requested runtime settings.

        Parameters:
            * model_size : faster-whisper model name or path.
            * device : Inference device, such as ``cpu`` or ``cuda``.
            * compute_type : Model computation precision.

        Returns:
            None.
        """
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
        """Check whether the speech-recognition model loaded successfully.

        Returns:
            ``True`` if the model is available; otherwise, ``False``.
        """
        return self.model is not None

    def transcribe(self, audio: np.ndarray) -> tuple[str, str | None]:
        """Transcribe mono audio.

        Parameters:
            * audio : Mono audio samples to transcribe.

        Returns:
            A pair containing transcript text and detected language. Returns
            empty text and ``None`` when transcription is unavailable or the
            input is too short.
        """
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
