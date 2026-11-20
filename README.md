# RobotSSL - Sound Source Localisation & Attention (Python)

RobotSSL is a robot audio-perception application.  It captures synchronised multichannel audio, estimates a speaker's direction, detects speech and wake words, transcribes utterances, tracks short attention sessions, and records event metadata.  It includes a Tkinter dashboard and experimental interfaces for robot communication.

Wake word detection and speech-to-text are optional dependencies, but are **strongly recommended** for normal use: without them, the application loses acoustic wake word detection or transcription-based interaction.  The core audio capture, speech segmentation, and direction-estimation pipeline can run without either library.

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
  -> wake word / transcript matching and attention tracking
  -> SQLite event record, dashboard update, and robot-interface commands
```

The XVF3800 profile expects six synchronised input channels at 16 kHz: channel 0 is ASR, channel 1 is the array sum, and channels 2-5 are the four raw microphones.  The current pipeline uses the raw microphones for detection, localisation, and transcription (after beamforming); it splits out the ASR and sum channels but does not yet feed them into later processing.  The DoA estimator uses the configured microphone geometry, not the XVF3800's on-device DoA.

## Requirements

- To run this project, you will need **Python 3.14 or later** preinstalled.
- You will also need a synchronised multichannel microphone array for useful DoA estimates.  Independent USB microphones may have unrelated clocks and latency and this program only supports a single microphone input.

To maximise the capabilities of the program, **the reSpeaker XVF3800 USB 4-Mic Array is heavily recommended** as the microphone array of choice.  It uniquely handles some audio cleaning, speech enhancement and beamforming, and sends out its own DoA and (boolean) speech recognition data via USB, which the program can read.  Since the program automatically seeks the reSpeaker XVF3800 on startup (if you've configured the program to use the XVF3800 - see (Configuration settings)[###configuration-settings] below), all you need to do to have the program read it is plug it into your computer and the program will automatically connect to it.

Note that in any case the microphone array must be connected to the computer directly (via USB port) in order to be readable by the program.

## Installation

First clone the repository code to your local computer to use it.  There is currently no pre-compiled build.

Although the program is a GUI-centric application, installation and start-up of the program is done through the console (unless you run the program in a specialised IDE or you compile the project - neither of those will be covered here.)

First, navigate to the project folder.  On Windows and Mac, you should be able to type `cd ` and then drag and drop the project folder into your console.

Then create a virtual environment: 

```bash
python3.14 -m venv .venv
```

Then activate the virtual environment.  Its activation procedure is system-dependent: 

```bash
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
```

Note that after this you should not need to envoke the specific Python (or pip) version, as it should point to the virtual environment's copy which should be the version of your desire.  

Then install the core dependencies.  The program will not run at all without these dependencies, usually exiting out safely before any operable part of the system completes loading.

```bash
python -m pip install -r requirements.txt
```

Also install the optional integrations.  Note that while they are "optional" in the sense that the program will run without their prescence, the components involved include some major capabilities of the program (including OpenWakeWord and faster-whisper) which severely limit the program's usefulness without their prescence.

Also note that some of the installation differs from platform to platform; Mac, Windows and Linux should all be able to install everything as necessary, however.

```bash
python -m pip install -r requirements-optional.txt
```

### Recommended speech and wake word features

`faster-whisper` provides local speech transcription.  The default `base` model may be downloaded the first time the app starts, so internet access may be needed once.  Use `--stt-model` to choose another supported model size or a local model path.  Transcription can be disabled by omitting the optional package; the app then continues with empty transcripts.

`openWakeWord` provides acoustic wake word detection.  The repository includes ONNX and TFLite model files under `data/`; the default ONNX path is configured in `robot_ssl/config.py`.  The first run may download openWakeWord's auxiliary models if they are missing.

On Linux, the optional requirements omit the openWakeWord package because its published dependency metadata requires TFLite Runtime, which has no Python 3.14 wheel.  Install the wrapper without dependencies to use the ONNX backend instead: 

```bash
python -m pip install --no-deps "openwakeword>=0.6"
```

The ONNX Runtime, `requests`, and `tqdm` dependencies are installed by the requirements files for this Linux workaround.  Use an `.onnx` wake word model; TFLite inference is not covered by this workaround.  On Windows and macOS, the optional requirements install openWakeWord normally.

The speech-to-text and wake word integrations are currently excluded by requirement markers on Python 3.15 because compatible ONNX Runtime wheels are not yet available there.  Other core functionality may still be installable, but those features will be unavailable.

## Configuration settings

Before using the program, you will also need to set the configuration settings (located at `config.json` in the root) to be adequate for your choice.  If you are not using the reSpeaker XVF3800, an aspect of this may involve measuring microphone positions in metres and ordered to match the raw microphone channels.

## Starting the program

The default configuration selects the XVF3800 profile.  Microphone geometry and processing settings are defined in `robot_ssl/config.py`; optional runtime overrides can be placed in the repository-root `config.json`.

If you are using the XVF3800, the program should be able to load adequately without any added parameters.  Note if you are not using the XVF3800, the program will load whatever `sounddevice` believes is the default-in for the computer, which may be the computer mic (and thus may not work as computers typically only have a single mic).

```bash
python main.py
```

If you wish to select a specific audio device, list the available audio devices and find the index or name of the device you wish to select (note that the default-in will be indicated with a `>`) - 

```bash
python main.py --list-devices
```

Then run the application, specifying the input device by index or name:

```bash
python main.py --device 2
```

There are several arguments to configure the program.  Several of them are also in the configuration file, provided as arguments for more temporary program configuration (though note that due to how the config code currently operates, any settings provided in the `config.json` override those in the arguments).  Use `--help` to view all available options.

`--use-general-mic-model` forces the program to not select the XVF3800 microphone profile, instead selecting the other microphone settings specified in the program and not attempting to read XVF3800 data.

Other useful options: 

```bash
python main.py --wakeword-model data/hey_jarvis_v0.1.onnx --stt-model base  # loads a custom model
python main.py --no-gui          # loads a CLI version of the program
python main.py --keep-chat-logs  # preserve previously stored event records after restart
python main.py --demo            # checks DoA estimation without opening an audio stream
```

Note on `keep-chat-logs` that by default (unless otherwise configured in `config.json`) the application clears stored events when it starts (see [Privacy and considerations](## Privacy and considerations) for more information).

The default wake word, if wake word detection is enabled, is “hey Jarvis”.  If wake word detection is disabled, the prorgam falls back to transcript phrase matching, which can recognise spoken phrases such as “hey robot” using faster-whisper if it is available (the phrase is different as Whisper generally finds it easier to transcribe phrases than names).  If STT is disabled too, there are no transcript-based wake phrases.

Microphone geometry is a unique attribute; it is the only configuration property which *must* currently be set in the command line arguments.  The appropriate command, `--mic-geometry`, takes a path to the JSON geometry file relative to the root.  An example, using the example geometry provided in the repository, is: 

```bash
python main.py --mic-geometry
```

Check that the geometry matches the physical microphone positions and the order of the raw microphone channels before interpreting azimuth results.

## Robot interface

Robot communication is non-conventional though is designed to be able to support nearly any type of robot interface.  `robot_ssl/interfaces/robot.py` opens a TCP socket using the `robot_host` and `robot_port` configuration settings and sends event data, currently robot alertness and rotation commands.  It is not a ROS interface and does not directly use a robot SDK.  A compatible server must be listening at the configured address, and the program to listen to the serial port must be running on a different console to the sender.  Review and adapt the protocol, coordinate conventions, limits, and safety behaviour for the target robot before connecting hardware.

To see example code that would be required to process the robot events, see `robot_gauge.py`; to test it, run it on a separate console from `main.py` (it should not matter which one is run first or last, with the specific way it is written, nor should it matter how many times either program is rerun - keep in mind if your program does not listen to the port in the same way, this may be different).

A notable benefit of this system is that the programs do not have to be in the same virtual environment.  This is beneficial when employing ROS 2, as it is a large codebase with some specific version requirements (currently in our testing, despite supposedly supporting Python 3.14/3.15, it currently requires a dependency which was deprecated completely by Python 3.12).  **They must, however, be the same host and port.**  (Currently the example listener program does not update its expected host and port, so if you update the sending host or port in configuration settings, you must update it in `robot_gauge.py` yourself).

## Optional accent-model training

The application reports an unknown accent unless a classifier is supplied with `--accent-model`.  The classifier must be a `joblib`-serialised scikit-learn-compatible model trained on five features in this order:

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

The included acoustic features and baseline speaker-continuity score are not reliable voice identity or accent verification.  Use consented, representative data and speaker-separated evaluation; do not treat these heuristics as proof of identity.

## Privacy and considerations

- SQLite stores transcripts and event metadata (direction, confidence, wake word/addressing decisions, language, timing, and voice-feature summaries).  Raw microphone audio is processed in memory and is not stored.
- Stored events are cleared at startup unless `--keep-chat-logs` is provided.  Protect the database and establish appropriate consent, retention, and deletion policies.
- The VAD and delay-and-sum beamformer are baselines.  Room reverberation, wind, clipping, poor calibration, array geometry, and robot noise can reduce accuracy.
- DoA assumes synchronised microphones and far-field speech.  A linear two-microphone array can have front/back ambiguity.
- Robot angle conventions, movement limits, emergency stops, and hardware safety interlocks must be implemented and validated for the target platform.

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

The tests use synthetic signals and temporary databases; they do not require a microphone or a connected robot.  The DoA demo is also available with `python main.py --demo`.

One can also independently test the robot event sending system by opening a new console and running 

```bash
python robot_gauge.py
```

This will open a window with a gauge.  Note that unmodified it displays the absolute orientation of the robot, *not* the severity of the robot's relative rotation.  This is to simulate how the robot would be positioned in a real life test, with the microphone being positioned on the rotating head.  To test the robot's relative rotation (or simulate the absolute orientation if the microphone array was stationary), go into `robot_gauge.py` and change the following line: 

```python
heading = (heading + turnby) % 360
```

to this: 

```python
heading = turnby % 360
```

and save and rerun.