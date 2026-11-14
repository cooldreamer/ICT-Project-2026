"""Operation management for the entire program."""

import argparse # for console-level argument parsing
import json # for loading and reading json files into dictionaries
import logging # for detailed logging of errors and warnings
from pathlib import Path
import queue
import threading
import time
import numpy as np

from robot_ssl.app import RobotAudioApp
from robot_ssl.config import AppConfig
from robot_ssl.audio.localization import SRPPHATLocalizer


def parse_args() -> argparse.Namespace:
    """Parse command-line options for capture, models, and integrations.

    Input channel configuration is derived from the microphone geometry rather
    than a separate channel-count option; the XVF3800 exposes additional
    non-microphone channels that require device-specific routing.

    Returns:
        The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Robot sound source localisation, wake-word, and speech attention pipeline")
    parser.add_argument("--device", help="Input device index (run --list-devices to inspect devices)")
    parser.add_argument("--use-general-mic-model", action="store_true", help="Forces program to use a general microphone model instead of the expected reSpeaker XVF3800 model")
    parser.add_argument("--mic-geometry", help="JSON file containing microphone positions in metres, channel order; format: [[x,y], ...]")
    parser.add_argument("--wakeword-model", help="Path to an openWakeWord ONNX/TFLite model; if omitted, transcript wake phrases are used")
    parser.add_argument("--wake-phrases", default="hey robot,hello robot,robot", help="Comma-separated transcript fallback phrases") # this should probably be taken out, since it's sort of the antithesis of how the program works
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


def load_geometry(path: str) -> tuple[tuple[float, float], ...] | None:
    """Load or select microphone coordinates.

    Parameters:
        * path : Optional JSON file containing microphone coordinate pairs.

    Returns:
        Microphone positions as ``(x, y)`` coordinate pairs.

    Raises:
        ValueError: If the microphone geometry is not supplied in a valid format/structure.
    """
    
    positions = None
    
    try:
        try:
            with open(path) as json_file:
                json_geometry = json.loads(path)
        except TypeError:
            raise FileNotFoundError
            
        positions = tuple(tuple(float(value) for value in pair) for pair in json_geometry)
        
        if any(len(point) != 2 for point in positions):
            raise ValueError("Microphone geometry must contain exactly one [x, y] pair per input channel")
    except FileNotFoundError:
        raise FileNotFoundError("JSON geometry file not found at input path")
    return positions # type: ignore (above check already enforces type match)


def list_audio_devices() -> None:
    """Print audio devices available through sounddevice.

    Raises:
        RuntimeError: If ``sounddevice`` is not installed.

    Returns:
        None.
    """
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Install sounddevice first: pip install sounddevice") from exc
    print(sd.query_devices())


def run_doa_demo(positions: tuple[tuple[float, float], ...]) -> int:
    """Synthesize a broadband signal at +40° and print estimated azimuth.

    Parameters:
        * positions : Microphone coordinate pairs in metres.

    Returns:
        Process status: 0 for a sufficiently accurate estimate, 1 for a failed
        or inaccurate estimate, or 2 if fewer than two microphones are given.
    """
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

### ~~~~~~~~~~~~~~~~~~~~~~~~ ###
### ~~~|------MAIN------|~~~ ###
### ~~~~~~~~~~~~~~~~~~~~~~~~ ###


def main() -> int:
    """Run the program depending on what command line arguments have been set.
    
    * If `--list-devices` is set, run the method to list available devices (see `list_audio_devices()`); 
    * If `--demo` is set, run the DoA demo and report its error; 
    * Otherwise, run the standard configured audio-perception application.

    Returns:
        The demo status, or 0 after the application exits normally.
    """
    
    returnval = 1
    
    args = parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
    )
    
    # If the action desired of the command is to list audio devices, run the function to list audio devices
    if args.list_devices:
        list_audio_devices()
        returnval = 0
    else: # Otherwise: 
        
        # Process positions from the mic geometry supplied, if any; otherwise positions is None
        positions = None
        try:
            positions = load_geometry(args.mic_geometry) # (will error here if mic geometry path or data is invalid)
        except FileNotFoundError:
            pass
        
        # Process device from supplied device argument
        device: int | str | None = args.device
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        
        # Set up the configuration settings object.  
        # (Note that special behaviour had to be written to make the default/JSON supplied values supersede empty argument entries.)
        config = AppConfig(
            **{key: value for key, value in {
                "use_xvf3800_mic_model": not args.use_general_mic_model,
                "_microphone_positions_m": positions,
                "wakeword_model_path": Path(args.wakeword_model),
                "stt_model": args.stt_model,
                "stt_device": args.stt_device,
                "stt_compute_type": args.stt_compute_type,
                "accent_model_path": args.accent_model,
                "robot_endpoint": args.robot_endpoint,
                "server_endpoint": args.server_endpoint,
                "database_path": Path(args.database),
                "log_level": args.log_level
            }.items() if value is not None}
        )
        config.validate() # (will error here if input settings are invalid)
        
        # If the action desired of the command is to run the program's test demo, run the demo and output its results
        if args.demo:
            returnval = run_doa_demo(config.microphone_positions_m)
        else: # Otherwise: 
            
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
    
    return returnval


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("Fatal error: %s", exc)
        raise SystemExit(1) from exc
