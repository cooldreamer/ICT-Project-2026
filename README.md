# RobotSSL - Sound Source Localisation & Attention (Python)

RobotSSL is a prototype robot audio-perception application. It captures synchronised multichannel audio, estimates a speaker's direction, detects speech and wake words, transcribes utterances, tracks short attention sessions, and records event metadata. It includes a Tkinter dashboard and experimental interfaces for robot communication.

Wake-word detection and speech-to-text are optional dependencies, but are **strongly recommended** for normal use: without them, the application loses acoustic wake-word detection or transcription-based interaction. The core audio capture, speech segmentation, and direction-estimation pipeline can run without either library.

## How the application works

```text
Microphone input
  -> frame capture and channel split
       -> XVF3800 raw microphone channels
            -> filtering, frame features, energy-based speech segmentation
            -> SRP-PHAT direction-of-arrival estimation
            -> delay-and-sum beamforming
            -> voice-feature extraction and optional accent classifier
            -> optional faster-whisper transcription
       -> configured XVF3800 ASR and sum channels (split out, not yet used downstream)
  -> optional openWakeWord detection on a selected raw microphone channel
  -> wake-word / transcript matching and attention tracking
  -> SQLite event record, dashboard update, and robot-interface commands
```

The XVF3800 profile expects six synchronised input channels at 16 kHz: channel 0 is ASR, channel 1 is the array sum, and channels 2-5 are the four raw microphones. The current pipeline uses the raw microphones for detection, localisation, and transcription (after beamforming); it splits out the ASR and sum channels but does not yet feed them into later processing. The DoA estimator uses the configured microphone geometry, not the XVF3800's on-device DoA.

## Requirements and installation

- Python 3.14 or later.
- A synchronised multichannel microphone array for useful DoA estimates. Independent USB microphones may have unrelated clocks and latency.
- Microphone positions measured in metres and ordered to match the raw microphone channels.

Create and activate a virtual environment, then install the core dependencies:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Install the optional integrations and test dependencies for your platform:

```bash
python -m pip install -r requirements-optional.txt
```

### Recommended speech and wake-word features

`faster-whisper` provides local speech transcription. The default `base` model may be downloaded the first time the app starts, so internet access may be needed once. Use `--stt-model` to choose another supported model size or a local model path. Transcription can be disabled by omitting the optional package; the app then continues with empty transcripts.

`openWakeWord` provides acoustic wake-word detection. The repository includes ONNX and TFLite model files under `data/`; the default ONNX path is configured in `robot_ssl/config.py`. The first run may download openWakeWord's auxiliary models if they are missing.

On Linux, the optional requirements omit the openWakeWord package because its published dependency metadata requires TFLite Runtime, which has no Python 3.14 wheel. Install the wrapper without dependencies to use the ONNX backend instead:

```bash
python -m pip install --no-deps "openwakeword>=0.6"
```

The ONNX Runtime, `requests`, and `tqdm` dependencies are installed by the requirements files for this Linux workaround. Use an `.onnx` wake-word model; TFLite inference is not covered by this workaround. On Windows and macOS, the optional requirements install openWakeWord normally.

The speech-to-text and wake-word integrations are currently excluded by requirement markers on Python 3.15 because compatible ONNX Runtime wheels are not yet available there. Other core functionality may still be installable, but those features will be unavailable.

## Configuration and running

The default configuration selects the XVF3800 profile and six-channel input. Microphone geometry and processing settings are defined in `robot_ssl/config.py`; optional runtime overrides can be placed in the repository-root `config.json`. Check that the geometry matches the physical microphone positions and the order of the four raw microphone channels before interpreting azimuth results.

List available audio devices:

```bash
python main.py --list-devices
```

Run the application, optionally specifying an input device by index or name:

```bash
python main.py
python main.py --device 2
```

The app attempts to find a reSpeaker XVF3800 device automatically when no device is specified. `--use-general-mic-model` selects the general microphone profile instead. Use `--help` to see all available options.

Useful options include:

```bash
python main.py --wakeword-model data/hey_jarvis_v0.1.onnx --stt-model base
python main.py --no-gui
python main.py --keep-chat-logs
python main.py --demo
```

The synthetic `--demo` checks DoA estimation without opening an audio stream. `--keep-chat-logs` preserves previously stored event records; by default the application clears stored events when it starts.

If wake-word detection is disabled, transcript phrase matching can still recognise phrases such as “hey robot” when STT is available. If STT is disabled too, there are no transcript-based wake phrases.

## Robot interface

Robot communication is experimental. `robot_ssl/interfaces/robot.py` opens a TCP socket using `robot_host` and `robot_port` from `AppConfig` and sends robot alertness and rotation commands. It is not a ROS interface and does not directly use a robot SDK. A compatible server must be listening at the configured address. Review and adapt the protocol, coordinate conventions, limits, and safety behaviour for the target robot before connecting hardware.

The project also contains `robot_ssl/interfaces/xvf_usb.py` for XVF3800 control transfers over USB. It is not currently used by the main audio pipeline.

## Optional accent-model training

The application reports an unknown accent unless a classifier is supplied with `--accent-model`. The classifier must be a `joblib`-serialised scikit-learn-compatible model trained on five features in this order:

1. Median pitch in Hz (0 when unavailable)
2. RMS in dBFS
3. Spectral centroid in Hz
4. 85% spectral roll-off in Hz
5. Zero-crossing rate

The optional trainer expects a CSV containing those features and an `accent` label:

```bash
python tools/train_accent_model.py data/accent_features.csv --model-out models/accent_classifier.joblib
python main.py --accent-model models/accent_classifier.joblib
```

The included acoustic features and baseline speaker-continuity score are not reliable voice identity or accent verification. Use consented, representative data and speaker-separated evaluation; do not treat these heuristics as proof of identity.

## Data, privacy, and limitations

- SQLite stores transcripts and event metadata (direction, confidence, wake-word/addressing decisions, language, timing, and voice-feature summaries). Raw microphone audio is processed in memory and is not stored by default.
- Stored events are cleared at startup unless `--keep-chat-logs` is provided. Protect the database and establish appropriate consent, retention, and deletion policies.
- The VAD and delay-and-sum beamformer are baselines. Room reverberation, wind, clipping, poor calibration, array geometry, and robot noise can reduce accuracy.
- DoA assumes synchronised microphones and far-field speech. A linear two-microphone array can have front/back ambiguity.
- Robot angle conventions, movement limits, emergency stops, and hardware safety interlocks must be implemented and validated for the target platform.
- Accent and speaker-continuity heuristics are not biometric speaker verification.

## Project layout

```text
main.py
robot_ssl/
  app.py                         # Audio pipeline and application orchestration
  config.py                      # Runtime settings and XVF3800 channel mapping
  config_ext/extMicIndices.py    # Named input-channel indices
  audio/
    processing.py                # Filtering, features, energy VAD and segmentation
    localisation.py              # SRP-PHAT-style azimuth estimator
    beamformer.py                # Direction-steered delay-and-sum beamforming
    wakeword.py                  # Optional openWakeWord adapter
    stt.py                       # Optional faster-whisper adapter
    characteristics.py           # Voice features and optional accent classifier
  interfaces/
    robot.py                     # Experimental TCP robot interface
    xvf_usb.py                   # XVF3800 USB controls (not used by main pipeline)
  services/
    storage.py                   # SQLite event storage
    health.py                    # Runtime counters
  gui/dashboard.py               # Tkinter live dashboard
tools/train_accent_model.py      # Optional accent-model training utility
tests/                           # Offline unit tests
```

## Tests

Install `requirements-optional.txt`, then run:

```bash
python -m pytest -q
```

The tests use synthetic signals and temporary databases; they do not require a microphone or a connected robot. The DoA demo is also available with `python main.py --demo`.
