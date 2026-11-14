# OrchardGuard — AI coding agent instructions

Read this file AND shared/schema.md before generating or editing code. Applies to all AI tools and agents (Codex, Cursor, Claude Code, etc.).

## Objective
Deliver a **native desktop PySide6 application**, not Streamlit, a web app, or a MuJoCo physics simulator. Demo a real CitrusFarm recorded orchard-robot trajectory, fault-tolerant wheel odometry + IMU + GPS localization, and synchronized X-Y and error plots. Interactive trees are *synthetic GNSS obstruction zones*, not measured geospatial canopy locations.

## Two-person work separation
- Backend agent / Person 1: exclusively edit `backend/`, related backend tests, and local ignored `data/`. Implement `backend.run.run_localization(scenario: dict) -> dict` using shared/schema.md. Do NOT edit frontend visuals.
- Frontend agent / Person 2: exclusively edit `frontend/` and frontend tests. Implement attractive, responsive native UI against `frontend.mock_data.generate_mock_results` and the fixed shared contract. Do NOT edit EKF, preprocessing, scenario physics.
- Shared: `shared/`, README.md, requirements.txt, AGENTS.md. Request coordination before changing. Avoid modifying shared files concurrently.
- Use independent Git branches: `feature/localization` and `feature/dashboard`. Pull requests to main, never force push, never replace other person's changes.

## Golden interface
- Function: `backend.run.run_localization(scenario: dict) -> dict`.
- Input JSON: `gps_quality` float 0–1; `outage_enabled` bool; `trees` array of {x, y, radius_m, severity}; `random_seed` int.
- Output: `metadata`, `frames`, `metrics`, as written in shared/schema.md. At minimum each frame has time, ground_truth, estimated, baseline, position_error, baseline_error, position_std_m, gps_status, gps_accepted, satellites.
- Coordinates: shared local metric ENU (x East, y North), yaw radians; timestamps seconds from replay start. No per-estimator best-fit alignment that hides drift.
- Backend may be unfinished and raise NotImplementedError; frontend MUST remain runnable in visible “MOCK DATA” mode until real output available.
- Ground truth may be used by the synthetic fault-zone detector to decide whether a canopy zone is entered; it MUST NOT be fused as an EKF measurement.
- The frontend may change and display scenario parameters, but backend owns GNSS noise, dropouts, gating, and filter recomputation.
- Never claim simulated satellite-count behavior is a calibrated GNSS model. Avoid made-up “sensor reliance percentages.”
- Only real measured metrics may be labeled CitrusFarm results. Mock or illustrative trajectories stay visibly labeled.

## Coding standards
1. Inspect existing files and git status/branch before editing.
2. Make the smallest tested change; do not refactor unrelated areas.
3. Keep APIs backwards compatible to shared/schema.md; validate contracts with tests.
4. Run `python -m unittest discover -s tests -v` before PR and report actual test result. Do not invent successful tests.
5. No unnecessary dependencies. Favor Python stdlib, PySide6, numpy for backend; add packages only with justification.
6. Keep GUI event loop nonblocking: expensive extraction or scenario runs must be precomputed or moved to a worker thread.
7. The user must be able to launch `python -m frontend.app` on macOS; support Windows/Linux where possible.
8. Preserve a visually useful mock mode for offline demos and rapid frontend development.
9. No fabricated numbers, fabricated sources, hidden failures, or silent fallbacks presented as real data.
10. Do not commit `.venv/`, caches, `.bag`, recordings, processed trajectories, video, API tokens, or secrets.

## Priority sequence
A. Backend: extract one overlapping CitrusFarm segment; align coordinates/time; wheel baseline; EKF; fault injection; measured metrics; interface output.
B. Frontend: working desktop window; orchard simulation; click-to-add trees; replay controls; X-Y trajectory; error-vs-time chart; show status; integration toggle.
C. Joint: connect real data, test stable scenario, fix discrepancies, freeze features, record <=2-minute demo.

## Scientific constraints
CitrusFarm contains postprocessed GPS reference (use for evaluation only) and recorded GPS data (sensor input). Source GNSS was reported as fixed-mode during collection; injected outages/outliers are synthetic and must be described so. An EKF without a new external position measurement will drift during a prolonged GNSS outage. If no improvement is measured, report the result honestly.

## Definition of done
App launches; graphical UI stays responsive; outputs match schema; replay and both plots are time synchronized; GNSS slider and tree zones create a scenario; measured data is distinguished from mock; tests pass; video/portal requirements are fulfilled.
