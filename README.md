# OrchardGuard

Native PySide6 desktop replay of CitrusFarm sensors. The operator view separates **measured error against the post-processed RTK reference**, estimated uncertainty, recorded GPS receiver health, and recommended speed. Ground truth never enters localization.

## Quick start

1. [Download the Sequence 01 sensor ZIP](https://github.com/rkhanna8/OrchardGuard/releases/download/v1.0.0/orchardguard-sensors.zip) (3.4 MB). Keep it zipped.
2. From a terminal, clone the repository and install the dependencies in a fresh Python environment:

```bash
git clone https://github.com/rkhanna8/OrchardGuard.git
cd OrchardGuard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m frontend.app --data "$HOME/Downloads/orchardguard-sensors.zip"
```

Adjust the ZIP path if your browser saved it elsewhere. On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and pass the actual ZIP path. You can also launch with `python -m frontend.app` and select the ZIP with **Open sensor ZIP**. A successful load shows **RECORDED · 01_13B_Jackal**. Launching without a recording starts in labeled mock mode.

Failed imports retain the active recording, scenario, and playback position with a visible error. Unchecking **Use recorded CitrusFarm sensors** explicitly selects mock mode.

## Operator controls

- **Orchard image**: clean registered Sequence 01 context, centered aspect-preserving cover. Drag to pan, scroll to zoom, click to add a synthetic obstruction zone. Imagery, trails, ellipse, scale, and clicks share one transform. The clean image is illustrative, not surveyed tree geometry. Unmatched sequences open **Metric view**.
- **RTK reference** is blue, gated estimate orange, ungated estimate pink, wheel baseline gray. The metric view also shows wheel+IMU in teal. The ellipse is always the 95% Gaussian model region; evaluation tolerance does not change it.
- The graph is **Position error at each moment (m)**, synchronized with the selected frame. Missing reference intervals appear as gaps. Whole-replay RMSE stays under **Evaluation**.
- Play/pause, restart, playback speed, and timeline scrub use the same frame for map, graph, GPS state, uncertainty and policy. Playback speed is independent of the recommended motion speed.
- **Recorded GPS**, **Simulated timed outage**, and **Simulated lateral jump** share initialization. Default fault interval is 30–60 s; default lateral jump is 10 m. Full-outage override blocks every GPS correction after initialization.
- **Simulated quality** adds seeded position noise and dropouts to the estimator GPS input. Clicked zones reduce that quality locally. It never changes recorded satellite counts. Reset restores quality 100%, no zones, and recorded GPS.
- Receiver counts come from the actual `receiver_state.num_sat` field. The latest preceding sample is shown with age; absent or older than 2 s is **Unavailable**.
- **Advisor is entirely offline**. It explains GPS loss/weakness/recovery, wheel+IMU prediction, the local speed decision, and measured replay error. No API key or network service is used.

## Policy settings

Normal / Slow / Stop recommend **100% / 35% / 0%** nominal speed during replay. Defaults:

| Condition | Slow | Stop |
|---|---:|---:|
| Horizontal covariance summary, sqrt(trace(Pxy)) | ≥1 m | ≥3 m |
| Time since a trusted GPS correction | ≥2 s | ≥8 s |

Escalation is immediate. Improvement requires **3 s sustained recovery per step**, Stop → Slow → Normal. Missing/stale prediction inputs also cause Stop. A noisy accepted correction refreshes trusted-fix age only after sustained innovation consistency: at least 10 accepted fixes spanning 2 s within a 3 s window, no accepted-sample gap over 0.8 s, mean innovation ≤0.75 m, mean NIS ≤3, window mean-noise RMS ≤0.5 m (sum of measurement covariance traces / sample count² ≤0.25 m²), and no reported receiver fault. Rejection resets this evidence. This policy observer does not change EKF updates or its recovery guard. Recorded replay continues when Stop is recommended. No LiDAR fallback has been validated, so it does not override this policy.

Change thresholds in **Fault timing / tolerance / policy**. Evaluation tolerance defaults to **1.0 m** and is independent of policy thresholds, the 95% ellipse, and the recovery guard's 2 m bound.

## Localization and integrity

Prediction continuously integrates wheel forward speed and bias-corrected IMU yaw rate, including while GPS is good. Initialization ends at the first 3 m of valid GPS travel: GPS position, course heading, stationary gyro bias, and a guarded wheel-speed calibration use only samples at/before that instant. For this ZIP, the causal speed scale is 0.9067396. It is shared by all comparisons. Unknown global initialization fails explicitly rather than fabricating a map pose.

Sequence 01 prediction accounts for the published GPS antenna offset, −0.18 m along body x relative to `base_link`. No per-estimator fitted alignment is applied. Wheel-only uses wheel yaw rate; wheel+IMU, ungated fusion, and gated EKF use IMU yaw rate. No ML is involved.

GPS corrections require finite valid positions, non-future/fresh timestamps and usable covariance. The existing 0.04 m² covariance floor remains; **known injected noise variance is now added**. The jump scenario deliberately preserves reported covariance/status. Ungated fusion has the same validity, freshness, covariance, controls and initialization; it bypasses the innovation/discontinuity guards.

The gated path uses NIS ≤9.21 plus a position-change consistency guard. Abrupt GPS discontinuities are quarantined. Recovery requires five fresh healthy fixes over 0.3–1.0 s, mutually consistent within 0.5 m and within 2 m of the wheel+IMU continuation of the last trusted fused pose. A bounded recovery update inflates covariance before a Joseph-form correction; it never hard-resets to a single fix. Large uncertain relocalizations are deliberately refused. This cannot detect every slowly varying GPS bias.

The reference and recorded GPS share an RTK source. Metrics are **error against the post-processed RTK reference**, not independent absolute accuracy. “Last GPS correction” and “Last trusted GPS fix” are displayed separately. Stop explanations name the actual threshold. The always-visible uncertainty card shows “Estimated chance within [tolerance] m” from the current covariance; detailed model probability and empirical coverage remain under Diagnostics, explicitly uncalibrated; values near one display `>99.9%`, never rounded `100.0%`. Covariance remains conservative in tested GPS-free intervals.

## ZIP import and local data

Legacy `wheel.csv`, `imu.csv`, `gps.csv`, `gt.csv` ZIPs remain supported. The reference header identifies the legacy sequence. Optional `metadata.json` supports other recordings:

```json
{
  "sequence": "02_13B_Jackal",
  "source": "citrusfarm",
  "reference_frame": "north_west",
  "sensor_sequences": {
    "wheel": "02_13B_Jackal", "imu": "02_13B_Jackal",
    "gps": "02_13B_Jackal", "gt": "02_13B_Jackal"
  }
}
```

Use `reference_frame: "enu"` if reference coordinates are already East/North. Optional `origin_lla: [latitude, longitude]` declares a shared origin; otherwise the first valid GPS position is the origin. Optional `time_bounds_unix_s: [start,end]` is checked against sensor streams. Conflicting sequence declarations, duplicate/mixed folders, malformed streams, unsupported frames, and insufficient overlap fail visibly. Sequence 01 imagery/default diagnostics require its known timestamp/origin fingerprint; they never carry into another sequence. Synthetic test ZIPs use `source: "fixture"` and show **FIXTURE · NOT MEASURED DATA**.

An optional timestamped `receiver_state.csv` inside the ZIP is used causally. Sequence 01 can also use ignored `data/receiver_state.csv`, or an explicit `ORCHARDGUARD_DIAGNOSTICS` path. `ORCHARDGUARD_DATA` supplies a backend default ZIP path. Fault zones reset on a successful new import; failed imports restore the active session.

Keep recordings, ZIPs, diagnostics, and generated replays in ignored `data/` or outside Git. The previously tracked sensor CSVs were removed from tracking; their local copies remain. No history was rewritten.

## Verification and reproduction

See **[evidence and limitations](docs/verification.md)** and **[all benchmark rows](docs/benchmark.csv)** for before/after errors, rejection cascades, coverage, 0.5/1/2 m tolerances, 10/30/60 s outages, full outage, and the real LiDAR trial.

```bash
ORCHARDGUARD_TEST_DATA="$HOME/Downloads/orchardguard-sensors.zip" \
  python -m unittest discover -s tests -v

python tools/benchmark.py \
  --zip "$HOME/Downloads/orchardguard-sensors.zip"

python tools/verify_desktop.py \
  --data "$HOME/Downloads/orchardguard-sensors.zip"
```

Real-data tests are explicitly skipped without `ORCHARDGUARD_TEST_DATA`. The desktop harness opens the actual window and activates the Open ZIP button, supplying chooser selections for reproducibility; it does not validate OS-native dialog interaction. Generated logs/screenshots stay in `data/`.

Inventory and experimental scan matching (NumPy/stdlib; the supplied bag is uncompressed):

```bash
python tools/inventory_bag.py \
  "/path/to/citrusfarm/01_13B_Jackal/base_2023-07-18-14-26-48_0.bag" \
  "/path/to/citrusfarm/01_13B_Jackal/odom_2023-07-18-14-26-48.bag"

python tools/lidar_baseline.py \
  --bag "/path/to/citrusfarm/01_13B_Jackal/base_2023-07-18-14-26-48_0.bag" \
  --zip "$HOME/Downloads/orchardguard-sensors.zip"
```

Optional receiver re-extraction uses `python -m backend.diagnostics BAG --output data/receiver_state.csv` and requires the optional `rosbags` package. The existing ZIP replay does not require that package or the bag.

## Two-minute walkthrough

1. **0:00–0:25:** Open Sequence 01, Recorded GPS, quality 100%. Explain RTK reference, estimate, measured error and uncertainty separately.
2. **0:25–0:55:** Timed outage; seek to 28 s and play through the fault. Show trusted-fix age, growing uncertainty and Slow → Stop while replay continues. Seek to 70 s for recovery.
3. **0:55–1:25:** Lateral jump; seek to 45 s. The receiver still reports RTK/satellites, but shifted fixes are rejected. Compare gated and ungated errors under Evaluation.
4. **1:25–1:50:** Reset, add a synthetic zone on the route, reduce quality, and explain the offline Advisor. Pan/zoom uses the same metric transform as the traces.
5. **1:50–2:00:** State limitations: correlated RTK evaluation, approximate illustrative image, one real sequence, and LiDAR matching that failed held-out validation.
