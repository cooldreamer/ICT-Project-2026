"""Application operation for the primary part of the robot audio-perception pipeline."""

import logging
import queue
import re
import threading
import time
from typing import Any, Tuple
import numpy as np

from robot_ssl.attention import AttentionMaintenanceSystem
from robot_ssl.audio.beamformer import DelayAndSumBeamformer
from robot_ssl.audio.characteristics import AccentClassifier, extract_voice_traits
from robot_ssl.audio.localization import SRPPHATLocalizer
from robot_ssl.audio.processing import AudioCleaner, SpeechSegmenter, extract_frame_features
from robot_ssl.audio.stt import SpeechToText
from robot_ssl.audio.wakeword import WakeWordDetector
from robot_ssl.config import AppConfig
from robot_ssl.interfaces.robot import ConsoleRobotInterface, HttpRobotInterface, RobotMovementInterface
from robot_ssl.interfaces.server import ServerInterface
from robot_ssl.models import AudioSegment, VoiceTraits # VoiceTraits is a settings class which does not seem to be being used, hmm...
from robot_ssl.services.health import HealthMonitor
from robot_ssl.services.storage import DatabaseStore


def circular_mean_degrees(angles: list[float]) -> float | None:
    """Calculate the circular mean of angles in degrees.

    Parameters:
        * angles : Angles in degrees to average.

    Returns:
        The mean angle in degrees, or ``None`` if ``angles`` is empty.
    """
    if not angles:
        return None
    radians = np.deg2rad(np.asarray(angles, dtype=np.float64))
    sin_mean = float(np.mean(np.sin(radians)))
    cos_mean = float(np.mean(np.cos(radians)))
    if abs(sin_mean) < 1e-9 and abs(cos_mean) < 1e-9:
        return float(angles[-1])
    return float(np.rad2deg(np.arctan2(sin_mean, cos_mean)))


class RobotAudioApp:
    """Coordinate audio capture, speech processing, attention, and integrations.

    Audio currently enters through ``sounddevice``. A device-specific XVF3800
    interface and explicit channel routing for DoA and wake-word processing are
    future integration work.
    """

    def __init__(
        self,
        config: AppConfig,
        event_queue: queue.Queue | None = None,
        stop_event: threading.Event | None = None,
        device: int | str | None = None,
        wake_phrases: tuple[str, ...] = ("hey robot", "hello robot", "robot"),
    ) -> None:
        """Initialize the pipeline components from configuration and options.

        Parameters:
            * config : Validated application settings.
            * event_queue : Optional queue for UI events and telemetry.
            * stop_event : Optional event used to request pipeline shutdown.
            * device : Optional sounddevice input device index or name.
            * wake_phrases : Transcript phrases recognized as wake words.

        Returns:
            None.
        """
        config.validate()
        self.config = config
        self.event_queue = event_queue
        self.stop_event = stop_event or threading.Event()
        self.device = device
        self.wake_phrases = tuple(p.lower().strip() for p in wake_phrases if p.strip())
        self.cleaner = AudioCleaner(config.sample_rate, config.raw_channels)
        
        self.localizer = SRPPHATLocalizer(
            config.microphone_positions_m,
            sample_rate=config.sample_rate,
            speed_of_sound_m_s=config.speed_of_sound_m_s,
            angle_step_degrees=config.doa_step_degrees,
        )
        
        self.beamformer = DelayAndSumBeamformer(
            config.microphone_positions_m,
            sample_rate=config.sample_rate,
            speed_of_sound_m_s=config.speed_of_sound_m_s,
        )
        
        self.segmenter = SpeechSegmenter(
            sample_rate=config.sample_rate,
            frame_samples=config.frame_samples,
            min_rms=config.vad_min_rms,
            noise_multiplier=config.vad_noise_multiplier,
            end_silence_seconds=config.vad_end_silence_seconds,
            pre_roll_seconds=config.vad_pre_roll_seconds,
            min_speech_seconds=config.vad_min_speech_seconds,
            max_segment_seconds=config.vad_max_segment_seconds,
        )
        
        self.wakeword = WakeWordDetector(
            config.wakeword_model_path,
            threshold=config.wakeword_threshold,
            cooldown_seconds=config.wakeword_cooldown_seconds,
        )
        
        self.attention = AttentionMaintenanceSystem(
            timeout_seconds=config.session_timeout_seconds,
            angle_tolerance_degrees=config.subject_angle_tolerance_degrees,
        )
        
        self.robot: RobotMovementInterface = (
            HttpRobotInterface(config.robot_endpoint) if config.robot_endpoint else ConsoleRobotInterface()
        )
        self.server = ServerInterface(config.server_endpoint)
        self.store = DatabaseStore(config.database_path)
        self.health = HealthMonitor()
        
        self.segment_queue: queue.Queue[AudioSegment] = queue.Queue(maxsize=6)
        
        self.last_azimuth: float | None = None
        self.last_doa_confidence: float = 0.0
        self.last_wakeword_score: float = 0.0
        
        self.last_ui_publish = 0.0
        
        return

    def _publish(self, event: dict[str, Any]) -> bool:
        """Publish an event to the optional UI queue without blocking capture.

        Parameters:
            * event : Event dictionary to publish.

        Returns:
            Success state of event publishing attempt.
        """
        
        published = False
        if self.event_queue is not None:
            try:
                self.event_queue.put_nowait(event)
                published = True
            except queue.Full:
                # Telemetry is expendable; discard its oldest queued item rather
                # than block microphone processing on a slow UI.
                try:
                    self.event_queue.get_nowait()
                    self.event_queue.put_nowait(event)
                    published = True
                except (queue.Empty, queue.Full):
                    pass
        return published

    def _hasTextWakeword(self, text: str) -> bool:
        """Check whether transcript text contains a configured wake phrase.

        Parameters:
            * text : Transcribed speech to search.

        Returns:
            Configured phrase present state.
        """
        lowered = re.sub(r"[^a-z0-9\s]", " ", text.lower())
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in self.wake_phrases)
    
    
    def _splitAudioData(self, frame_data) -> Tuple[np.ndarray | None, np.ndarray | None, np.ndarray]:
        """Splits audio frame data into asr, sum and raw mics depending on config settings.
        
        Parameters:
            * frame_data : Raw audio data in all channels.

        Returns:
            Tuple of 3 Numpy arrays: 
            * ASR (automatic speech recognition) (1D array)
            * sum (total single channel audio input) (1D array)
            * mics/raw (all raw mic inputs) (2D array)
        """
        asr_frame, sum_frame, mics_frame = None, None, None
        if self.config.microphone_channel_indices.asr is not None:
            asr_frame = frame_data[:, self.config.microphone_channel_indices.asr]
        if self.config.microphone_channel_indices.sum is not None:
            sum_frame = frame_data[:, self.config.microphone_channel_indices.sum]
        mics_frame = frame_data[:, self.config.microphone_channel_indices.raw]
        
        return (asr_frame, sum_frame, mics_frame)


    # To Do: 
    # * Replace direct sounddevice interface with specialised reSpeaker XVF3800 interface library
    def run(self) -> None:
        """Capture microphone frames and enqueue completed speech segments.

        Returns:
            None.

        Raises:
            RuntimeError: If the ``sounddevice`` dependency is unavailable.
            Exception: If audio capture or processing fails; the original error
                is logged, published, and re-raised.
        """
        try:
            import sounddevice as sd
        except ImportError as exc:
            self._publish({"type": "error", "message": "Missing sounddevice. Install requirements.txt first."})
            raise RuntimeError("Missing dependency: sounddevice; run `pip install -r requirements.txt`") from exc

        worker = threading.Thread(target=self._segmentWorker, name="speech-segment-worker", daemon=True)
        worker.start()
        self.robot.set_alertness("idle", "audio perception starting")
        self._publish({
            "type": "status",
            "message": "Listening for speech. Wake-word model: " + ("enabled" if self.wakeword.enabled else "disabled; transcript fallback active"),
        })

        try:
            print("# channels:", self.config.input_channels)
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.input_channels,
                blocksize=self.config.frame_samples,
                dtype="float32",
                device=self.device,
            ) as stream:
                logging.info("Audio stream started: %s Hz, %s channels", self.config.sample_rate, self.config.input_channels)
                while not self.stop_event.is_set():
                    raw_frame, overflowed = stream.read(self.config.frame_samples)
                    if overflowed:
                        self.health.audio_overflows += 1
                    
                    asr_frame, sum_frame, mics_frame = self._splitAudioData(raw_frame)
                    
                    cleaned = self.cleaner.clean(mics_frame)
                    features = extract_frame_features(cleaned, self.config.sample_rate)
                    per_channel_rms = np.sqrt(np.mean(cleaned.astype(np.float64) ** 2, axis=0))
                    wake_mono = cleaned[:, int(np.argmax(per_channel_rms))]
                    wakeword_detected, wake_score = self.wakeword.detect(wake_mono)
                    self.last_wakeword_score = wake_score

                    doa_angle: float | None = None
                    doa_confidence: float | None = None
                    # Avoid spending CPU localising very quiet frames.
                    if self.config.raw_channels >= 2 and features.rms >= self.config.vad_min_rms * 0.5:
                        result = self.localizer.localize(cleaned)
                        if result is not None:
                            doa_angle = result.azimuth_degrees
                            doa_confidence = result.confidence
                            self.last_azimuth = doa_angle
                            self.last_doa_confidence = doa_confidence

                    segment = self.segmenter.process(
                        cleaned,
                        rms=features.rms,
                        doa_angle=doa_angle,
                        wakeword_detected=wakeword_detected,
                        doa_confidence=doa_confidence,
                    )
                    if segment is not None:
                        try:
                            self.segment_queue.put_nowait(segment)
                        except queue.Full:
                            self.health.dropped_segments += 1
                            logging.warning("Speech segment queue full; dropped an utterance")

                    self.health.record_frame()
                    now = time.monotonic()
                    if now - self.last_ui_publish >= 0.20:
                        self._publish({
                            "type": "telemetry",
                            "azimuth_degrees": self.last_azimuth,
                            "doa_confidence": self.last_doa_confidence,
                            "rms_dbfs": features.rms_dbfs,
                            "wakeword_score": self.last_wakeword_score,
                            "wakeword_enabled": self.wakeword.enabled,
                            "attention_active": self.attention.active,
                            "health": self.health.snapshot(),
                        })
                        self.last_ui_publish = now
        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received")
        except Exception as exc:
            logging.exception("Audio capture or processing failed: %s", exc)
            self._publish({"type": "error", "message": f"Audio capture failed: {exc}"})
            raise
        finally:
            self.stop_event.set()
            worker.join()
            self.store.close()
            self.robot.set_alertness("idle", "audio perception stopped")

    def _segmentWorker(self) -> None:
        """Load optional speech models and process queued segments until shutdown.

        Returns:
            None.
        """
        stt = SpeechToText(
            model_size=self.config.stt_model,
            device=self.config.stt_device,
            compute_type=self.config.stt_compute_type,
        )
        try:
            accent_classifier = AccentClassifier(self.config.accent_model_path)
        except Exception:
            logging.exception("Could not load accent classifier; using unknown labels")
            accent_classifier = AccentClassifier()

        while not self.stop_event.is_set() or not self.segment_queue.empty():
            try:
                segment = self.segment_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._handleSegment(segment, stt, accent_classifier)
            except Exception:
                logging.exception("Could not process speech segment")
                self._publish({"type": "error", "message": "Could not process one speech segment; see log for details."})
            finally:
                self.segment_queue.task_done()

    def _handleSegment(self, segment: AudioSegment, stt: SpeechToText, accent_classifier: AccentClassifier) -> None:
        """Analyze an utterance, update attention, and publish its event.

        Parameters:
            * segment : Captured utterance with audio and localization data.
            * stt : Speech-to-text backend used for transcription.
            * accent_classifier : Optional classifier for acoustic traits.

        Returns:
            None.
        """
        angle = circular_mean_degrees(segment.doa_angles_degrees)
        confidence = float(np.mean(segment.doa_confidences)) if segment.doa_confidences else 0.0
        if confidence < 0.02:
            confidence = 0.0
        beamformed = self.beamformer.beamform(segment.samples, angle)
        traits = extract_voice_traits(beamformed, self.config.sample_rate)
        text, language = stt.transcribe(beamformed)
        traits.language = language
        try:
            traits.accent_guess, traits.accent_confidence = accent_classifier.predict(traits)
        except Exception:
            logging.exception("Accent model prediction failed")
            traits.accent_guess = "unknown (accent model prediction failed)"
            traits.accent_confidence = None

        text_wakeword = self._hasTextWakeword(text)
        wakeword_confirmed = bool(segment.wakeword_detected or text_wakeword)
        if wakeword_confirmed:
            score = 1.0
            addressed = True
            self.attention.engage(angle, traits)
            self.robot.set_alertness("attending", "wake word detected")
        elif self.attention.active:
            score = self.attention.assess_continuation(angle, traits, speech_detected=True)
            addressed = score >= 0.55
            if addressed:
                self.robot.set_alertness("attending", "subject appears to be continuing")
        else:
            score = 0.0
            addressed = False

        if addressed and angle is not None:
            self.robot.orient_camera(angle, score, "wakeword" if wakeword_confirmed else "continued_subject_speech")
        elif text:
            self.robot.set_alertness("alert", "speech heard but not identified as addressing the robot")

        event = {
            "type": "segment",
            "timestamp_unix": time.time(),
            "transcript": text,
            "language": language,
            "azimuth_degrees": angle,
            "doa_confidence": confidence,
            "wakeword_detected": wakeword_confirmed,
            "addressed_robot": addressed,
            "attention_score": score,
            "duration_seconds": segment.duration_seconds,
            "voice_traits": traits.as_dict(),
            "stt_available": stt.available,
            "attention_active": self.attention.active,
        }
        self.store.save_event(event)
        self.server.send_event(event)
        self._publish(event)
        logging.info(
            "speech=%r | azimuth=%s | wakeword=%s | addressing_robot=%s | attention=%.2f",
            text,
            f"{angle:+.1f}°" if angle is not None else "unknown",
            wakeword_confirmed,
            addressed,
            score,
        )
