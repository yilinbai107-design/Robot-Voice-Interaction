# Designing Robot Voices for Welcome and Wayfinding Tasks

An exploratory study of pitch, loudness and intonation.

Yilin Bai — MA Creative Robotics, Creative Computing Institute, University of the Arts London. Final Major Project, 2026.

## Project overview

This desktop robot is a controlled research prototype for comparing perceived naturalness, appropriateness and comfort of prerecorded robot voices across two simulated university service tasks. It is not an autonomous conversational robot.

- **Welcome:** “Hello, I am here to help you.”
- **Wayfinding:** “Go straight ahead, then turn left to reach the classroom.”

Each participant completes six blocks (two tasks × three acoustic parameters), each containing an original voice and two modified versions. The application rotates task order, parameter order and voice positions using a local participant counter. Participants listen in A–B–C order, rate each voice on three seven-point scales and choose a preferred version.

## Repository contents

| Path | Purpose |
| --- | --- |
| `experiment_app_v9_display_fix.py` | Final desktop application: serial input, audio playback, animated face, touchscreen evaluation and CSV logging |
| `Pico_Project/main.py` | MicroPython firmware for physical buttons |
| `Audio_Files/Welcome/` | Seven unique Welcome audio stimuli |
| `Audio_Files/Wayfinding/` | Seven unique Wayfinding audio stimuli |
| `requirements.txt` | Desktop Python dependencies |
| `.gitignore` | Excludes local research records and common temporary files |

## Hardware

- Raspberry Pi Pico with MicroPython installed
- Three momentary push-buttons, wired between GPIO and GND (internal pull-up inputs)
- Five-inch touchscreen, connected to the host computer using HDMI and USB touch/data connections as appropriate
- Speaker connected to the host audio output
- Host Windows computer and 3D-printed robot enclosure

| Button | Pico GPIO | Serial message |
| --- | --- | --- |
| A | GP16 | `BUTTON_A` |
| B | GP17 | `BUTTON_B` |
| C | GP18 | `BUTTON_C` |

The Pico transmits button events over USB serial. The Python application handles playback and screen feedback on the host computer.

## Setup and running (Windows)

1. Install Python 3.12 with Tkinter support (included in the standard Windows Python installation).
2. Download or clone this repository, preserving its directory structure.
3. Install the desktop dependencies from the repository root in PowerShell:

   ```powershell
   py -m pip install -r requirements.txt
   ```

4. Using a MicroPython-compatible tool such as Thonny, save `Pico_Project/main.py` onto the Pico as `main.py`. Reconnect/reset the Pico so it runs automatically. Close any other serial monitor before connecting the desktop application.
5. Connect the touchscreen and speaker. For the secondary-screen kiosk layout, use Windows extended-display mode and select the intended audio output in Windows.
6. Launch the application from the repository root:

   ```powershell
   py -u .\experiment_app_v9_display_fix.py
   ```

7. Select the Pico serial port in the application (the original default is `COM7`, at 115200 baud). Use the port refresh/connect controls, then select Start Study. Follow the scenario prompts and listen to A, B and C in order before evaluating the voices.

For software testing without the Pico, keyboard A/B/C can substitute for the physical buttons. F11 toggles fullscreen; Escape exits fullscreen/kiosk mode; Ctrl+Shift+Q closes the application. The secondary-display detection is Windows-specific.

## Audio stimuli

`W_` denotes Welcome and `D_` denotes Wayfinding. `V0` is the original voice; `P1/P2`, `L1/L2` and `I1/I2` denote the two pitch, loudness and intonation variants respectively. Each task uses seven unique files, reusing its original voice across the three parameter blocks. Audio is prerecorded, not generated live by the robot.

## Data and ethics

The application creates `Research_Data/` locally when it starts a session. It writes `voice_ratings_v9_study.csv` and maintains `participant_sequence_v9.txt`. The CSV retains a legacy `clarity` field that is left empty; the implemented evaluation dimensions are naturalness, appropriateness and comfort.

Participant records, consent forms and raw research data are deliberately excluded from this repository. Aggregate descriptive results are included in `Data/`; see `Data/data_notes.md` for the provisional sample selection and calculation notes. Do not publish them or commit local test sessions. Any further data sharing or research use must comply with the applicable consent and ethics arrangements. The supplied audio files should only be publicly distributed if their source/licence permits redistribution.

## Development acknowledgement

OpenAI ChatGPT assisted with programming guidance, code development/refinement and troubleshooting. The repository contains the supplied project implementation, not a new reconstruction of the experiment.
