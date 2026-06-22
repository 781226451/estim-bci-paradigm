# estim-bci-paradigm

PsychoPy-based electrical stimulation paradigm for BCI experiments with separate
doctor-side and patient-side clients. The two clients are designed to run on
different computers and communicate through Lab Streaming Layer (LSL) via
`pylsl`.

The current rating scale is visual analog scale-depression, abbreviated as
VAS-D.

## Overview

- `doctor.py`: controls stimulation rounds, sends state commands, receives VAS-D
  ratings, and writes CSV data.
- `patient.py`: waits for the doctor client, displays stimulation and VAS-D rating
  screens, and sends ratings back through LSL.
- `doctor_config.toml`: runtime settings for the doctor client.
- `patient_config.toml`: runtime settings for the patient client.

The patient client only enters the experiment screen after it detects the
doctor-side LSL command stream.

## Requirements

- Python 3.11
- PsychoPy
- pylsl
- uv

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`.

## Setup

Install or sync the environment:

```powershell
uv sync
```

If Windows Firewall prompts for network access, allow Python/LSL on the local
network. Both computers must be on the same LAN, and the LSL stream names in the
two config files must match.

## Running

On the doctor computer:

```powershell
uv run .\.venv\Scripts\python.exe .\doctor.py
```

On the patient computer:

```powershell
uv run .\.venv\Scripts\python.exe .\patient.py
```

Start the doctor client first, then start the patient client. The doctor client
enables stimulation only after the patient client is connected and sending
`READY` messages.

## Configuration

Doctor-side settings live in `doctor_config.toml`; patient-side settings live in
`patient_config.toml`.

Important sections:

- `[screen]`: fullscreen/window-mode settings.
- `[monitor]`: PsychoPy monitor profile name.
- `[lsl]`: command and rating stream names plus discovery timing.
- `[rating]`: rating scale full name, abbreviation, range, and step size.
- `[font]`: font used by PsychoPy text stimuli.

The two computers run independently, so there is no per-role screen-number
setting. Each client uses the primary display on its own computer.

## Experiment Flow

1. Doctor starts a stimulation round.
2. Patient screen switches to "stimulating".
3. Doctor ends stimulation.
4. Patient enters the VAS-D rating screen.
5. Patient submits a configured VAS-D rating. VAS-D means visual analog
   scale-depression, and the default range is 0-100.
6. Doctor client records the rating to CSV and advances to the next round.

## Data Output

The doctor client writes CSV files under `data/`. The output includes subject
metadata, round number, VAS-D rating, stimulation timestamps, rating submission
time, rating receive time, and stimulation duration.

Generated data files are ignored by Git.
