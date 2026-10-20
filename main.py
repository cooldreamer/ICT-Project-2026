"""Launch the robot sound-localisation and attention pipeline."""
from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
import queue
import sys
import threading
import time
import numpy as np

from robot_ssl.app import RobotAudioApp
from robot_ssl.config import AppConfig, DEFAULT_MIC_POSITIONS
from robot_ssl.audio.localization import SRPPHATLocalizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Robot sound source localisation, wake-word, and speech attention pipeline")
    parser.add_argument("--device", help="Input device index (run --list-devices to inspect devices)")
    parser.add_argument("--channels", type=int, default=4, help="Input channels; must match the connected microphone array")
    parser.add_argument("--mic-geometry", help="JSON file containing microphone positions in metres, channel order; format: [[x,y], ...]")
    parser.add_argument("--wakeword-model", help="Path to an openWakeWord ONNX/TFLite model; if omitted, transcript wake phrases are used")
    parser.add_argument("--wake-phrases", default="hey robot,hello robot,robot", help="Comma-separated transcript fallback phrases")
    parser.add_argument("--stt-model", default="base", help="faster-whisper model size/path (e.g. tiny, base, small)")
    parser.add_argument("--stt-device", default="cpu", choices=("cpu", "cuda"), help="faster-whisper inference device")
    parser.add_argument("--stt-compute-type", default="int8", help="faster-whisper compute type, e.g. int8 or float16")
    parser.add_argument("--accent-model", help="Optional joblib-serialized scikit-learn-compatible accent classifier")
    parser.add_argument("--robot-endpoint", help="Optional HTTP endpoint that accepts generic JSON robot commands")
    parser.add_argument("--server-endpoint", help="Optional HTTP endpoint to receive perception events")
    parser.add_argument("--database", default="data/robot_audio.sqlite3", help="SQLite database path")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    parser.add_argument("--no-gui", action="store_true", help="Run without Tkinter dashboard")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    parser.add_argument("--demo", action="store_true", help="Run a synthetic DoA sanity check without a microphone")
    return parser.parse_args()


def load_geometry(path: str | None, channels: int) -> tuple[tuple[float, float], ...]:
    if path:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        positions = tuple(tuple(float(value) for value in pair) for pair in raw)
    else:
        if channels == len(DEFAULT_MIC_POSITIONS):
            positions = DEFAULT_MIC_POSITIONS
        elif channels == 1:
            positions = ((0.0, 0.0),)
        else:
            raise ValueError(
                f"No default geometry for {channels} channels. Supply --mic-geometry with one [x,y] pair per channel."
            )
    if len(positions) != channels or any(len(point) != 2 for point in positions):
        raise ValueError("Microphone geometry must contain exactly one [x, y] pair per input channel")
    return positions


def list_audio_devices() -> None:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Install sounddevice first: pip install sounddevice") from exc
    print(sd.query_devices())


def run_doa_demo(positions: tuple[tuple[float, float], ...]) -> int:
    """Synthesize a broadband signal at +40° and print estimated azimuth."""
    if len(positions) < 2:
        print("DoA demo needs at least 2 microphone positions; use 3+ non-collinear microphones for best results.")
        return 2
    sample_rate = 16_000
    n_samples = 8_192
    expected_angle = 40.0
    rng = np.random.default_rng(7)
    source = rng.normal(0.0, 0.1, n_samples)
    source_spectrum = np.fft.rfft(source)
    frequencies = np.fft.rfftfreq(n_samples, 1.0 / sample_rate)
    theta = np.deg2rad(expected_angle)
    direction = np.array([np.cos(theta), np.sin(theta)])
    audio = []
    for position in np.asarray(positions, dtype=np.float64):
        arrival_delay = -float(np.dot(position, direction)) / 343.0
        shifted_spectrum = source_spectrum * np.exp(-1j * 2.0 * np.pi * frequencies * arrival_delay)
        audio.append(np.fft.irfft(shifted_spectrum, n=n_samples))
    multichannel = np.column_stack(audio).astype(np.float32)
    localizer = SRPPHATLocalizer(positions, sample_rate=sample_rate, angle_step_degrees=1.0)
    result = localizer.localize(multichannel)
    if result is None:
        print("DoA demo failed: no usable localisation result")
        return 1
    print(f"Synthetic source: {expected_angle:+.1f}° | estimated: {result.azimuth_degrees:+.1f}° | score: {result.confidence:.3f}")
    error = abs((result.azimuth_degrees - expected_angle + 180.0) % 360.0 - 180.0)
    print(f"Absolute azimuth error: {error:.1f}°")
    return 0 if error <= 8.0 else 1


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
    )
    if args.list_devices:
        list_audio_devices()
        return 0

    positions = load_geometry(args.mic_geometry, args.channels)
    if args.demo:
        return run_doa_demo(positions)

    device: int | str | None = args.device
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    config = AppConfig(
        channels=args.channels,
        microphone_positions_m=positions,
        wakeword_model_path=args.wakeword_model,
        stt_model=args.stt_model,
        stt_device=args.stt_device,
        stt_compute_type=args.stt_compute_type,
        accent_model_path=args.accent_model,
        robot_endpoint=args.robot_endpoint,
        server_endpoint=args.server_endpoint,
        database_path=Path(args.database),
        log_level=args.log_level,
    )
    config.validate()
    events: queue.Queue = queue.Queue(maxsize=200)
    stop_event = threading.Event()
    app = RobotAudioApp(
        config,
        event_queue=events,
        stop_event=stop_event,
        device=device,
        wake_phrases=tuple(part.strip() for part in args.wake_phrases.split(",")),
    )
    worker = threading.Thread(target=app.run, name="robot-audio-app", daemon=False)
    worker.start()

    if not args.no_gui:
        try:
            from robot_ssl.gui.dashboard import Dashboard
            Dashboard(events, stop_event).run()
        except ImportError:
            logging.exception("Tkinter is unavailable; switching to console monitoring")
            try:
                while worker.is_alive():
                    time.sleep(0.4)
            except KeyboardInterrupt:
                stop_event.set()
    else:
        try:
            while worker.is_alive():
                while True:
                    try:
                        event = events.get_nowait()
                    except queue.Empty:
                        break
                    if event.get("type") == "segment":
                        print(
                            f"Transcript={event.get('transcript')!r}, azimuth={event.get('azimuth_degrees')}, "
                            f"wakeword={event.get('wakeword_detected')}, addressed_robot={event.get('addressed_robot')}"
                        )
                    elif event.get("type") in ("status", "error"):
                        print(f"{event.get('type', '').upper()}: {event.get('message', '')}")
                time.sleep(0.15)
        except KeyboardInterrupt:
            stop_event.set()
    stop_event.set()
    worker.join()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("Fatal error: %s", exc)
        raise SystemExit(1) from exc
