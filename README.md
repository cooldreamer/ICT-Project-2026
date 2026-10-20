# Robot Sound Source Localisation & Attention (Python)

A modular starter implementation of the requested robot audio-perception pipeline. It combines synchronised multichannel audio capture, SRP-PHAT-style direction-of-arrival (DoA) estimation, a delay-and-sum beamformer, optional wake-word ML, local speech-to-text, acoustic speech characteristics, an attention-session tracker, a robot movement adapter, optional server event forwarding, SQLite metadata storage, health counters, and a Tkinter dashboard.

## 1. Pipeline overview

```text
Synchronized mic array
  -> Audio stream / input interface
  -> Cleaning + frame features + energy VAD
  -> SRP-PHAT azimuth estimation ------------------------------+
  -> Wake-word model (optional)                                |
  -> Speech segmenter                                          |
       -> Direction-steered delay-and-sum beamformer <----------+
       -> faster-whisper STT (optional)
       -> Pitch / timbre-proxy features + optional accent model
       -> Wake phrase + continued-subject speech scoring
            -> Alertness state + camera/head orientation command
            -> SQLite event record + optional server POST
            -> GUI / health dashboard
```

## 2. Requirements and installation

- Python 3.10 or later.
- A **synchronised multichannel microphone array** (usually a USB array or a multichannel audio interface) for useful DoA estimates. Several unrelated USB microphones are not automatically synchronised; their independent clocks and latencies can make phase/time-difference methods unreliable.
- Microphone positions measured in metres, expressed relative to the robot, in the same order as the input channels.

Install the core dependencies:

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Install optional speech recognition and wake-word packages:

```bash
python -m pip install -r requirements-optional.txt
```

`faster-whisper` loads the selected speech model when the application starts. The first run may need internet access to obtain the model if it is not already cached. For wake-word ML, obtain a compatible ONNX or TFLite model and pass its file path. For example, the openWakeWord project documents pre-trained models and its Python API at <https://github.com/tslapp/openwakeword> and <https://pypi.org/project/openwakeword/>. A model file is not bundled here.

## 3. Configure microphones

List devices and supported input channels:

```bash
python main.py --list-devices
```

The included `example_mic_geometry.json` is only an illustrative 10 cm square array. Replace the coordinates with measurements for your physical array. Its convention is **x = robot-forward, y = robot-left**, so 0° means in front of the robot and positive angles mean left.

Run the synthetic DoA check without opening a microphone:

```bash
python main.py --demo
```

Run with a four-channel input device (replace `2` with the correct device index):

```bash
python main.py --device 2 --channels 4 --mic-geometry example_mic_geometry.json
```

Enable an installed wake-word model and change STT model size, for example:

```bash
python main.py --device 2 --channels 4 \
  --mic-geometry example_mic_geometry.json \
  --wakeword-model models/hey_robot.onnx \
  --stt-model base
```

On Windows PowerShell, enter the command on one line or use PowerShell's backtick for line continuation instead of `\\`.

For a console-only launch, add `--no-gui`. If the wake-word model is omitted, the app uses transcript matching for phrases such as “hey robot”, “hello robot”, or “robot”. Transcript matching needs a working STT backend. Without `faster-whisper`, the localisation loop can still run and a configured wake-word model can still trigger attention, but text transcripts and text-only wake-word fallback are unavailable.

## 4. Robot movement / camera integration

By default, `ConsoleRobotInterface` only logs simulated camera/head movements; it **does not actuate physical hardware**. To connect your robot, implement `RobotMovementInterface` in `robot_ssl/interfaces/robot.py` with the robot's SDK, ROS 2 action/topic, or motor controller. Alternatively, `--robot-endpoint URL` enables a generic JSON HTTP adapter. It POSTs a payload like:

```json
{
  "command": "orient_camera",
  "azimuth_degrees": 34.0,
  "attention_score": 1.0,
  "reason": "wakeword",
  "timestamp_unix": 1780000000.0
}
```

The exact endpoint schema must match your robot gateway. Test it in a simulated environment before enabling hardware movement. The adapter's alertness messages use `{"command":"set_alertness", "state":"attending", ...}`.

An optional `--server-endpoint URL` receives JSON perception events. Keep such endpoints authenticated and on a trusted network; the example intentionally leaves authentication and transport-security policy to the deployment.

## 5. Speech characteristics and accent model

The included feature extractor estimates median pitch (where voiced periodicity is detectable), RMS level, spectral centroid, spectral roll-off, and zero-crossing rate. These are basic acoustic descriptors, **not a reliable voice identity or accent determination**. The application reports an unknown accent unless a trained classifier is supplied with `--accent-model PATH`.

That file must be a `joblib`-serialized scikit-learn-compatible classifier trained to accept a feature vector in this exact order:

1. median pitch in Hz (0 when unavailable)
2. RMS in dBFS
3. spectral centroid in Hz
4. 85% spectral roll-off in Hz
5. zero-crossing rate

A production accent classifier should be trained and evaluated with consented, appropriately representative speech data. A starter train/test script is provided in `tools/train_accent_model.py`. It expects a CSV with the five feature columns above plus an `accent` label; run `python tools/train_accent_model.py data/accent_features.csv --model-out models/accent_classifier.joblib`, then pass `--accent-model models/accent_classifier.joblib` when launching the app. Its random holdout report is illustrative only: for serious evaluation, split by speaker so the same speaker does not appear in both train and test. The small baseline speaker-continuity score uses angular consistency and acoustic-feature similarity; it is not a biometric speaker-verification ML model. For crowded or safety-critical environments, replace it with a validated speaker embedding / diarisation model and stronger VAD.

## 6. Data storage, privacy, and logging

- SQLite records the transcript, estimated direction, confidence score, wake-word/addressing decisions, speech-feature summary, language, and timing. The storage service supports both saving events and loading recent history.
- Raw audio is kept in memory for segment processing and is **not written to disk by default**.
- Transcripts and acoustic features can still be sensitive. Set database access controls, retention and deletion rules, and consent notices appropriate to your use case.
- Runtime performance counters include frames/second, input overflows, processing errors, dropped segments, and uptime.

## 7. Project layout

```text
main.py
robot_ssl/
  app.py                         # Integration and worker pipelines
  config.py                      # Audio/DoA/VAD settings and array geometry
  models.py                      # Shared event/feature records
  attention.py                   # Addressing + continued-speaker tracking baseline
  audio/
    processing.py                # Cleaning, frame features, energy VAD
    localization.py              # SRP-PHAT-style azimuth estimator
    beamformer.py                # Direction-steered delay-and-sum
    wakeword.py                  # Optional openWakeWord adapter
    stt.py                       # Optional faster-whisper adapter
    characteristics.py           # Speech features + accent-model adapter
  interfaces/
    robot.py                     # Console and HTTP robot adapters
    server.py                    # Optional event POST interface
  services/
    storage.py                   # SQLite event records
    health.py                    # Runtime monitoring counters
  gui/dashboard.py               # Tkinter dashboard
```

## 8. Limitations to address before production

1. **Array calibration:** this demo assumes far-field speech and a known planar 2-D microphone layout. A linear two-mic array can have front/back ambiguity. Poor geometry, reverberation, wind, clipping, or robot self-noise will reduce accuracy.
2. **Independent microphones:** use a shared audio clock or calibrate and continually compensate for inter-device sample-rate/latency drift.
3. **VAD and beamforming:** the included energy VAD and simple frequency-domain delay-and-sum beamformer are baselines. Test on your robot's own noise and room acoustics; consider stronger VAD and adaptive beamforming.
4. **Addressing decision:** only a confirmed wake word or transcript wake phrase starts attention. Afterwards, the baseline uses direction and acoustic-feature consistency for an 8-second session. Do not use this heuristic as proof of speaker identity.
5. **Robot control:** camera angles, coordinate signs, limits, velocity profiles, safety interlocks, and emergency stops are robot-specific and must be added in the hardware adapter.
6. **Latency:** speech-to-text is performed in a separate worker thread so the real-time capture loop can continue. If utterances arrive faster than inference, the bounded queue drops excess segments and increments a health counter.

## 9. Tests

Install core requirements, then run:

```bash
python -m pytest -q
```

The synthetic DoA demo can also be run directly with `python main.py --demo`.
