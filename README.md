# OrchardGuard

Native desktop localization demonstrator for the UIUC Precision & Digital Agriculture Hackathon (Robotics Challenge 1).

**Current state:** Qt desktop frontend runs using **SYNTHETIC mock data**. Do not present it as CitrusFarm localization output until connected to the real backend.

## Run

Python 3.10 or later.

```bash
git clone https://github.com/rkhanna8/OrchardGuard.git
cd OrchardGuard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m frontend.app
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. PySide6 creates a separate native application window, **not a website**.

### Controls
Play/pause, restart, speed control, simulated GNSS quality slider, click anywhere in the orchard to add a virtual canopy-degradation zone, and clear trees. Two synchronized plots compare true/estimated trajectories and position error over time. Real backend integration is not yet implemented; UI runs on a reproducible demonstration scenario.

## Work split
- Localization: `backend/`; preprocessing CitrusFarm, wheel+IMU baseline, EKF, fault injection, evaluation, exported contract.
- Desktop UI: `frontend/`; Qt visuals, input controls, playback, graphs, session management. Start with `frontend/mock_data.py`.
- Shared: `shared/schema.md`, `AGENTS.md`, requirements, and integrations. Coordinate before changing them.

## Branches and checks
```bash
git switch -c feature/localization
# teammate instead uses: git switch -c feature/dashboard
python -m unittest discover -s tests -v
```

Do not commit datasets, `.bag` files, large outputs, secrets, or virtual environments. See `AGENTS.md`.

**Challenge deadline:** Sunday Nov 15, 2026, 12:00 PM (per track PDF); demo video max two minutes.

Dataset: https://ucr-robotics.github.io/Citrus-Farm-Dataset/
