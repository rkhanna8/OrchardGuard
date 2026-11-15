# OrchardGuard

Native PySide6 localization dashboard for CitrusFarm Sequence 01 (`01_13B_Jackal`). Replays recorded wheel, IMU and GPS sensors; compares gated EKF, ungated GPS fusion, wheel + IMU, and wheel odometry against the post-processed RTK reference. No physical robot actuation.

## Launch on this Mac

From this checkout:

```bash
cd ~/Documents/OrchardGuard
/tmp/orchardguard-qt-test/bin/python -m frontend.app --data "$HOME/Documents/orchardguard-sensors.zip"
```

Or run `/tmp/orchardguard-qt-test/bin/python -m frontend.app`, then **Open sensor ZIP**. The ZIP must contain `wheel.csv`, `imu.csv`, `gps.csv`, and `gt.csv` (nested ZIP folders are supported). Without a ZIP, the app starts in clearly labeled **MOCK DATA** mode. A failed real-data computation displays an error and retains the previous display; it never silently substitutes mock results. Uncheck **Use recorded CitrusFarm sensors** to explicitly enter mock mode.

The verified interpreter is temporary and may disappear after reboot or `/tmp` cleanup. The old project `.venv` is not the supported launch environment. On a fresh computer, use a supported Python with `python -m pip install -r requirements.txt`, then `python -m frontend.app`. No web server, ROS installation, or API key is required for replay.

## Dashboard

- Large registered orchard image and a metric-view tab. Blue: post-processed RTK reference; orange: gated EKF; pink: ungated fusion; gray: wheel odometry. The metric view additionally shows wheel + IMU in muted teal. The ellipse is the EKF's 95% horizontal Gaussian model region.
- Error chart, map markers, GNSS decisions, confidence, and speed policy use the same replay frame. Play/pause, restart, 1–8× speed, and seeking are supported. Whole-replay RMSE and peak metrics are explicitly labeled as whole-replay summaries.
- **Controls**: adjust simulated quality, force a full outage, change canopy-zone radius, click the map to add synthetic obstruction zones, clear zones, or reset the scenario. Processing runs in a worker; results from superseded requests are discarded. Quality changes apply when the slider is released.
- **Fault timing / tolerance / policy** configures timed faults, jump magnitude, evaluation tolerance and sustained recovery, and Slow/Stop thresholds.
- **Evaluation** compares all four estimators. **Advisor** shows Gemini explanations when configured, otherwise a deterministic local explanation.

## Three scenarios and scientific interpretation

All comparisons share GPS position initialization after the first 3 m of GPS travel, course-derived heading, and a stationary-segment gyro bias. Synthetic faults begin after this initialization. If no valid fresh global initialization is possible, real replay fails explicitly instead of displaying a fabricated global pose.

1. **Recorded GPS**: valid fresh fixes, reported covariance with a conservative 0.04 m² eigenvalue floor, and a 2-D innovation gate (NIS threshold 9.21). Keep quality at 100%, full outage off, and no canopy zones for an unmodified recorded scenario.
2. **Simulated timed outage**: default 30–60 s after initialization; no GPS correction enters either fusion estimator during the interval. Wheel + IMU prediction continues and uncertainty grows.
3. **Simulated lateral jump**: default 10 m displacement from 30–60 s, perpendicular to the common initial GPS course. Reported status and covariance are preserved. Gated and ungated fusion receive the same observations and validity/freshness checks; only the innovation gate differs.

Optional quality/canopy degradation introduces seeded position noise and dropouts into estimator GPS inputs only. Receiver diagnostics remain recorded context, so FIXED_RTK and many satellites can coexist with an injected fault. Tree locations are synthetic obstruction zones, not measured canopy.

The `baseline` is wheel forward speed integrated with wheel yaw rate. A separate `wheel_imu` comparison uses forward speed and bias-corrected IMU yaw rate. The EKF uses these wheel/IMU controls with GPS corrections. Ground truth is used only for visualization, evaluation, and synthetic zone entry, never as a filter measurement. No estimator is retrospectively aligned to conceal drift.

GPS and reference share an RTK source: metrics are **error against the post-processed RTK reference**, not an independent absolute-accuracy assessment. Position confidence is the probability inside the chosen tolerance under a centered Gaussian with the current EKF horizontal covariance; it is a **model estimate**, not measured confidence calibration. `position_std_m = sqrt(trace(Pxy))` is a covariance summary, not a one-axis standard deviation.

During-fault time within tolerance uses left-held replay errors clipped to the fault interval. Recovery is measured from fault end until the estimator has continuously stayed within tolerance for the configured dwell (default 3 s); that dwell is included in recovery time. If no sustained recovery occurs before replay end, the display says **did not recover**. A dead-reckoning baseline may re-enter tolerance due to route geometry, despite having no correcting measurement.

## Data verification and receiver diagnostics

The supplied sensor ZIP covers approximately 180 s; initialization leaves 169.2 s / 1,693 displayed frames. The reference extends beyond this segment; replay uses only overlapping sensor/reference time. Wheel, IMU, and GPS replay use `bag_time_ns / 1e9`. GPS header time is used only to reject stale/inconsistent fixes (default 1 s). Wheel speed is body-forward; positive IMU z yaw rate agrees with wheel yaw rate (correlation about 0.910). All estimators use the same GPS-course ENU heading.

Reference conversion is east = −ty, north = tx, with the common first-GPS origin. No fitted shift/rotation is used for evaluation. On the supplied overlap, recorded GPS/reference discrepancy has a median of about 0.011 m and maximum 0.026 m, consistent with their shared RTK source. Full audit values are returned in `metadata.audit`.

Optional local diagnostics were extracted from:

```text
~/Documents/citrusfarm/01_13B_Jackal/base_2023-07-18-14-26-48_0.bag
```

`data/receiver_state.csv` contains 6,865 bag-timestamped messages from `/piksi/debug/receiver_state` (`piksi_rtk_msgs/ReceiverState_V2_4_1`). Its inspected definition explicitly names `num_sat`, `rtk_mode_fix`, `fix_mode`, system/IO/SwiftNAP error flags, and antenna-present flag. No satellite count is inferred from the quality slider. The app uses the latest preceding sample only, with a 2 s staleness limit; missing/stale diagnostics display unavailable. The ZIP alone is sufficient.

To reproduce extraction, install optional `rosbags` into your chosen environment, then run:

```bash
python -m backend.diagnostics \
  "$HOME/Documents/citrusfarm/01_13B_Jackal/base_2023-07-18-14-26-48_0.bag" \
  --output data/receiver_state.csv
```

`ORCHARDGUARD_DATA` selects a default ZIP for backend use; `ORCHARDGUARD_DIAGNOSTICS` overrides the optional CSV path. Raw sensor files, diagnostic CSVs, ZIPs, bags, and generated screenshots/results stay local and ignored. Sensor CSVs previously tracked on main are removed from tracking on this integration branch, with local files preserved; existing Git history is not rewritten.

## Map registration

The original user-supplied `seq01.png` is included in `frontend/assets/`. Its **white route is baked into the figure**, not a second live estimate. Six route correspondences spread across the full reference define a display-only affine registration. Five withheld turns have approximately 1.4–4.8 pixel residuals, about 0.11–0.39 m at the image scale. This is approximate route correspondence, not surveyed georegistration. The generated cleaned image is not used. Metric positions and errors are never calculated in image coordinates. Controls/check points are in `frontend/map_registration.py`.

Source: [CitrusFarm sequence figures](https://ucr-robotics.github.io/Citrus-Farm-Dataset/sequence.html).

## Local demo policy and Gemini

The deterministic policy recommends Normal, Slow, or Stop using covariance summary and age of the last accepted fix. Defaults: Slow at 1 m uncertainty or 2 s fix age; Stop at 3 m or 8 s. Escalation is immediate. Improvement requires 3 s sustained recovery per downward step (Stop → Slow → Normal). Seeking reuses precomputed decisions. Stop is displayed as **Auto-stop triggered · replay continues**; the policy never changes the recorded robot trajectory.

Optional Gemini configuration:

```bash
export GEMINI_API_KEY='your-key'
export GEMINI_MODEL='gemini-2.5-flash'   # optional override
/tmp/orchardguard-qt-test/bin/python -m frontend.app --data "$HOME/Documents/orchardguard-sensors.zip"
```

Do not commit keys. API calls run in a separate worker on meaningful state changes, are rate-limited and time-limited, and stale replies cannot replace newer state. Snapshot time is labeled. Structured dashboard values are sent to the Gemini GenerateContent REST API; the model writes advisory text only. Missing keys, network/API failures, and empty responses use the deterministic local summary. The local policy owns every speed decision. Live Gemini requires a usable key and network access; neither is necessary for the demo.

## Tests

```bash
ORCHARDGUARD_TEST_DATA="$HOME/Documents/orchardguard-sensors.zip" \
  /tmp/orchardguard-qt-test/bin/python -m unittest discover -s tests -v
```

Without `ORCHARDGUARD_TEST_DATA`, real-recording checks are explicitly skipped. Tests cover the original mock contract, faults, gating, confidence, causal diagnostics, sustained recovery, policy transitions, Gemini fallback, stale UI/API results, input isolation, and real replay serialization. A reference-perturbation test confirms that reference changes cannot alter the estimate.

Optional native integration check (opens and closes a window, writes ignored screenshots):

```bash
/tmp/orchardguard-qt-test/bin/python tools/verify_desktop.py \
  --data "$HOME/Documents/orchardguard-sensors.zip"
```

## Two-minute demo

- **0:00–0:25** — Open the ZIP with Recorded GPS, quality 100%, no zones. Play at 4×. Explain blue RTK reference, orange EKF, gray wheel baseline, and that the RTK reference is correlated with recorded GPS.
- **0:25–0:55** — Select Simulated timed outage, seek to 28 s, and play through 60 s. Show accepted-fix age, expanding ellipse, model confidence, Slow then Stop, and continued replay. Seek to 70 s to show sustained recovery.
- **0:55–1:25** — Select Simulated lateral jump, seek to 45 s. Show recorded FIXED_RTK/satellites alongside innovation rejection. Compare pink ungated drift with orange gated prediction and open Evaluation.
- **1:25–1:50** — Reset, click a canopy zone on the route, and replay through it. Explain synthetic fault entry and background recomputation. The local policy remains deterministic; the Advisor explains only.
- **1:50–2:00** — State limitations: correlated RTK evaluation, approximate map registration, and inevitable dead-reckoning drift during long outages. No physical actuation.
