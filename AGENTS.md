# OrchardGuard — AI Coding Agent Instructions

Read this file and shared/schema.md before making changes.

## 1. Project Objective

Build a complete, polished, native PySide6 desktop application for the UIUC Precision & Digital Agriculture Hackathon, Robotics Challenge 1.

OrchardGuard demonstrates fault-tolerant localization for an agricultural robot operating in an orchard using real CitrusFarm recorded sensor data.

The application must:
- Replay real orchard robot trajectories.
- Estimate robot position using wheel odometry, IMU, and GPS.
- Demonstrate EKF-based sensor fusion.
- Simulate GNSS degradation and outages under orchard canopy.
- Compare estimated position against recorded ground truth.
- Visualize localization accuracy and sensor diagnostics.
- Provide an interactive, professional desktop interface.

This is a native desktop application, NOT a website, Streamlit application, or MuJoCo simulator.

Hackathon deadline: November 15, 2026, 12:00 PM.
Demo video maximum: 2 minutes.

## 2. Agent Ownership

The Codex agent is responsible for the ENTIRE application.

Codex may freely inspect, modify, and integrate:
- backend/
- frontend/
- shared/
- tests/
- tools/
- README.md
- requirements.txt

Backend and frontend development do NOT need to be isolated.

Prioritize complete end-to-end functionality over artificial separation between components.

However:
- Preserve existing working functionality.
- Inspect git status before modifying files.
- Do not overwrite another contributor's uncommitted work.
- Avoid unnecessary refactoring.
- Keep shared interfaces consistent.
- Do not force-push or perform destructive Git operations.
- Do not delete datasets or recordings without explicit permission.

## 3. Data and Localization

Use the real CitrusFarm dataset.

Required pipeline:
1. Load a recorded orchard robot trajectory.
2. Extract synchronized GPS, wheel odometry, IMU, and ground-truth data.
3. Convert coordinates into a consistent local metric ENU frame.
4. Establish a wheel-odometry baseline.
5. Implement EKF-based localization.
6. Apply configurable synthetic GNSS degradation.
7. Recompute estimated trajectories for each scenario.
8. Calculate localization errors and evaluation metrics.
9. Export results through the shared interface.

Primary API:

backend.run.run_localization(scenario: dict) -> dict

Follow shared/schema.md.

Ground truth must NEVER be fused into the localization estimator.

Ground truth may be used to determine entry into synthetic canopy zones and to evaluate localization accuracy.

Never apply per-estimator best-fit trajectory alignment that conceals drift.

Do not invent sensor measurements, experimental results, or performance improvements.

## 4. GNSS Diagnostics

Integrate real receiver diagnostics where available.

Display:
- GNSS fix type.
- RTK status.
- Satellite count.
- GNSS measurement acceptance or rejection.
- Estimated position uncertainty.
- Current localization error.
- GNSS outage or degradation status.

Clearly distinguish:
- Recorded sensor measurements.
- Synthetic fault injection.
- Estimated quantities.
- Ground-truth reference data.

Do not claim synthetic satellite-count behavior represents a calibrated GNSS receiver model.

Do not invent sensor-reliance percentages.

## 5. Desktop Frontend Requirements

Use PySide6.

The interface must be polished, visually cohesive, responsive, and suitable for a live technical demonstration.

Use a professional dark dashboard theme with consistent typography, spacing, colors, and visual hierarchy.

### Primary Layout

A. Main orchard trajectory visualization:
- Large central X-Y plot.
- Ground-truth trajectory.
- EKF estimated trajectory.
- Wheel-odometry baseline.
- Clearly differentiated colors and legend.
- Current robot position marker.
- Current estimated position marker.
- Interactive synthetic canopy zones.
- Click to add canopy zones.
- Clear/reset canopy zones.
- Equal X/Y scaling in meters.

B. Localization error visualization:
- Separate synchronized graph.
- Position error versus elapsed time.
- EKF and baseline errors.
- Current playback-time indicator.
- Readable axis labels and units.

C. Diagnostics panel:
- GNSS/RTK status.
- Satellite count where recorded.
- Localization error.
- RMSE and other measured metrics.
- Position uncertainty.
- GPS measurement acceptance/rejection.
- Current scenario status.

D. Playback and scenario controls:
- Play/pause.
- Restart.
- Playback speed.
- Timeline scrubber.
- GNSS quality slider.
- Synthetic outage toggle.
- Canopy-zone controls.
- Scenario reset.

### Visual Quality

Prioritize:
- Clean dashboard composition.
- Readable charts and labels.
- Consistent spacing.
- High contrast.
- Professional status indicators.
- Responsive resizing.
- Smooth playback.
- Clear distinction between measured and simulated information.

Avoid:
- Cluttered layouts.
- Overlapping widgets.
- Tiny text.
- Unnecessary popups.
- Placeholder visualizations presented as real results.
- Blocking the GUI during processing.

## 6. Frontend and Backend Integration

The frontend must consume the actual backend output through shared/schema.md.

At minimum, each frame includes:
- time
- ground_truth
- estimated
- baseline
- position_error
- baseline_error
- position_std_m
- gps_status
- gps_accepted
- satellites

The application must support:
- Real dataset replay.
- Synthetic scenario modifications applied to real recorded data.
- Clearly labeled mock mode if real data is unavailable.

Mock mode must never silently replace failed real-data processing.

Scenario changes must trigger backend recomputation when necessary.

Heavy processing must not block the Qt event loop.

Existing modules such as diagnostics, evaluation, recording, map registration, settings, advisor, and policy should be inspected and integrated where useful.

Do not create redundant modules without justification.

## 7. Scientific Integrity

The CitrusFarm dataset includes recorded GNSS measurements and postprocessed GPS reference data.

Use recorded measurements as estimator inputs and reference data for evaluation only.

Synthetic canopy obstructions, outages, and GNSS outliers must be explicitly labeled as simulated.

Do not claim real canopy locations were measured if they were generated interactively.

EKF localization may drift during prolonged GNSS outages.

Report actual measured results, including cases where EKF does not outperform the baseline.

Do not fabricate accuracy improvements.

## 8. Python Environment

The verified working macOS Python environment is:

/tmp/orchardguard-qt-test/bin/python

Launch the application using:

/tmp/orchardguard-qt-test/bin/python -m frontend.app

This environment is temporary and may not persist across reboots or cleanup.

The original project .venv experienced Qt Cocoa plugin discovery failures.

Do not repeatedly troubleshoot that environment.

Do not modify Qt plugin file flags, reinstall PySide6, or recreate Python environments unless explicitly requested.

If the verified environment becomes unavailable, report the issue rather than entering a repair loop.

## 9. Debugging and Token Efficiency

CRITICAL: Avoid excessive token consumption.

- Never enter an unbounded debugging loop.
- After TWO unsuccessful attempts at the same problem, STOP.
- Report the exact error and likely cause.
- Do not repeatedly launch a crashing GUI application.
- Prefer isolated unit tests over repeated GUI launches.
- Do not repeatedly inspect the same files without a reason.
- Avoid dumping large files or logs into context unnecessarily.
- Use targeted file searches and concise command output.
- Do not repeatedly reinstall dependencies.
- Do not repeatedly modify operating-system settings.
- Make small, targeted changes.
- Preserve working functionality.
- Never claim a test passed unless it actually passed.

For GUI verification:
- Prefer unit tests and static inspection.
- Run the full application at most once per meaningful change.
- If GUI initialization fails, stop rather than repeatedly retrying.

## 10. Testing

Before substantial changes:
- Inspect git status.
- Inspect existing tests.
- Identify current working functionality.

Run:

/tmp/orchardguard-qt-test/bin/python -m unittest discover -s tests -v

Validate:
- Shared schema consistency.
- Backend replay.
- Localization evaluation.
- Fault injection.
- Frontend/backend integration.
- Playback synchronization.
- Correct distinction between real and mock data.

Report actual test results.

Do not invent successful tests.

## 11. Development Priorities

Priority 1: Preserve the currently working application.

Priority 2: Complete real CitrusFarm dataset integration.

Priority 3: Ensure backend localization and evaluation work correctly.

Priority 4: Connect backend results to the frontend.

Priority 5: Complete and polish the desktop dashboard.

Priority 6: Verify playback, charts, diagnostics, and controls.

Priority 7: Run tests and fix critical issues.

Priority 8: Update README and prepare the hackathon demonstration.

Do not spend time implementing speculative features before the core application works.

## 12. Git and File Safety

Never:
- Run git reset --hard without explicit permission.
- Run git clean -fd without explicit permission.
- Force-push.
- Delete recorded datasets without permission.
- Overwrite another contributor's work.
- Commit virtual environments.
- Commit large sensor recordings.
- Commit secrets or credentials.

Respect .gitignore.

Keep changes focused and reviewable.

## 13. Definition of Done

The project is complete when:

1. The native desktop application launches successfully.
2. Real CitrusFarm data is loaded and replayed.
3. Wheel odometry and EKF localization operate correctly.
4. Ground-truth and estimated trajectories appear together.
5. Localization error appears in a synchronized second graph.
6. GNSS degradation and canopy zones affect localization.
7. Diagnostics reflect actual available receiver information.
8. Playback and scenario controls function.
9. The GUI remains responsive.
10. Mock and real results are clearly distinguished.
11. Automated tests pass.
12. The application is ready for a live hackathon demonstration.

## 14. Agent Operating Principle

Work toward a complete, reliable, scientifically defensible application.

Prioritize working integration and demonstration quality.

Do not confuse additional code with meaningful progress.

When encountering an environmental problem, diagnose it efficiently and stop after two failed attempts.

The goal is a finished OrchardGuard application, not an endless debugging session.
