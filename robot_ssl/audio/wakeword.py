"""Optional openWakeWord integration with a safe disabled fallback."""

import logging
from pathlib import Path
import time
import numpy as np
import os


class WakeWordDetector:
    """Optional openWakeWord adapter with threshold and cooldown handling."""
    
    @property
    def enabled(self) -> bool:
        """Check whether a wake-word model is ready for inference.

        Returns:
            ``True`` if a model is loaded; otherwise, ``False``.
        """
        return self.model is not None

    def __init__(self, model_path: Path | None, threshold: float = 0.5, cooldown_seconds: float = 2.0) -> None:
        """Load a wake-word model when a model path is provided.

        Parameters:
            * model_path : Optional ONNX or TFLite model path.
            * threshold : Minimum model score required to trigger.
            * cooldown_seconds : Minimum time between wake-word triggers.

        Returns:
            None.

        Raises:
            RuntimeError: If a model path is provided but `openwakeword` is not installed.
            FileNotFoundError: If a model path is provided but no file exists at the provided path.
            ValueError: If a valid model path is provided but the file type is not a supported file type (.onnx or .tflite).
        """
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.last_trigger = 0.0
        self.model = None
        self.model_name: Path | None = None
        
        if model_path:
            try:
                from openwakeword.model import Model
                from onnxruntime.capi.onnxruntime_pybind11_state import NoSuchFile
            except ImportError as e:
                raise RuntimeError(
                    "A wake-word model path was supplied. Install the optional dependency with: pip install openwakeword"
                ) from e
            
            if os.path.exists(model_path):
                if model_path.suffix in (".onnx", ".tflite"):
                    if model_path.suffix != ".onnx":
                        logging.warning("As of this version of the program, the latest version of openwakeword to support .tflite is currently severely outdated due to an unupdated dependency.  This may not work; use a .onnx model instead for assured compatibility.")
                    
                    try:
                        self.model = Model(wakeword_models=[str(model_path)], inference_framework="onnx" if model_path.suffix == ".onnx" else "tflite")
                    except NoSuchFile as e:
                        import openwakeword.utils
                        openwakeword.utils.download_models()
                        try:
                            self.model = Model(wakeword_models=[str(model_path)], inference_framework="onnx" if model_path.suffix == ".onnx" else "tflite")
                        except NoSuchFile as e:
                            print("Model load failed!  Trace printed below in case the error message does not display it.")
                            print(e)
                            raise FileNotFoundError("The openwakeword library itself likely does not have the background models it needs.  An attempt was made to install them already, but for one reason or another this did not successfully install the libraries.  Please ensure your library folder has adequate permissions and then install them yourself by running openwakeword.utils.download_models() in Python!"
                                                    ) from e
                    else:
                        print("I have model!!!")
                else:
                    raise ValueError("Incompatible file type detected - openwakeword only supports .onnx and .tflite (though .onnx is recommended for this program)")
                
                self.model_name = model_path
                logging.info("Loaded wake-word model: %s", model_path)
            else:
                raise FileNotFoundError("Wake word model at specified path does not exist!")
        
        return

    def detect(self, mono_audio: np.ndarray) -> tuple[bool, float]:
        """Run wake-word detection on a mono audio frame.

        Parameters:
            * mono_audio : Mono float audio samples for detection.

        Returns:
            A tuple containing whether a threshold-crossing trigger occurred and
            the highest model score for this input.
        """
        event = False
        best_score = 0.0
        
        if self.model is not None:
            mono = np.asarray(mono_audio, dtype=np.float32).reshape(-1)
            pcm = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
            # openWakeWord accepts 16 kHz, 16-bit PCM frames; buffering here means
            # callers may use a frame size other than the model's usual 80 ms.
            if not hasattr(self, "_pending"):
                self._pending = np.empty(0, dtype=np.int16)
            self._pending = np.concatenate((self._pending, pcm))
            
            chunk_samples = 1280
            while self._pending.size >= chunk_samples:
                chunk = self._pending[:chunk_samples]
                self._pending = self._pending[chunk_samples:]
                prediction = self.model.predict(chunk)
                scores = (prediction[0] if prediction else {}) if isinstance(prediction, tuple) else prediction
                score = max((float(v) for v in dict(scores).values()), default=0.0)
                best_score = max(best_score, score)
                now = time.monotonic()
                if score >= self.threshold and now - self.last_trigger >= self.cooldown_seconds:
                    event = True
                    self.last_trigger = now
        
        return event, best_score
