# Sequence 01 verification — 2026-11-15

Branch: `integration/sequence01-desktop`. Changes are in the local working tree; no push or PR was made. Commands and the two-minute walkthrough are in [README](../README.md). Full numerical results, all four estimators and 0.5/1/2 m tolerances are in [benchmark.csv](benchmark.csv). Large opportunity logs and replay products remain ignored under `data/`.

## Data and synchronization

The real input was `~/Documents/orchardguard-sensors.zip`, Sequence `01_13B_Jackal`. Replay uses bag timestamps in seconds, not sensor-header timestamps. Reference north/west coordinates convert to shared East/North; no estimator-specific fitted alignment is used. The GPS/reference coordinate audit found median separation about 0.011 m and maximum 0.026 m. Wheel/IMU yaw-rate correlation was 0.910. These sources share RTK: all errors below are **against the post-processed RTK reference**, not independent absolute-position accuracy.

Initialization uses only preceding samples: stationary gyro bias −0.00177098671 rad/s and GPS course 1.54416435 rad after 3 m of travel. It ends at Unix 1689715619.71423. GPS chord 3.06305794 m / wheel travel 3.37810102 m gives scale 0.906739593. The straightness guard measured 0.11597 rad accumulated absolute rotation. All comparators use this same initialization and scale. A future-GPS perturbation regression verifies earlier outputs and calibration remain unchanged. Prediction continues with wheel+IMU during good GPS and outage; stale controls are explicitly marked and uncertainty increases.

The published [base-to-LiDAR calibration](https://ucr-robotics.s3.us-west-2.amazonaws.com/citrus-farm-dataset/Calibration/results/05-baselink-lidar-result.txt) and [LiDAR-to-GPS calibration](https://ucr-robotics.s3.us-west-2.amazonaws.com/citrus-farm-dataset/Calibration/results/04-lidar-gps-result.txt) imply antenna x = −0.18 m relative to base. Prediction and its Jacobian account for this lever arm. See the [dataset calibration index](https://ucr-robotics.github.io/Citrus-Farm-Dataset/calibration.html).

Receiver extraction produced 6,865 samples. Display uses actual `num_sat`, with latest-preceding alignment and a 2 s staleness limit. Satellite count does not override innovation checks. ZIP-only operation remains supported.

## Screenshot investigation and rejection cascade

Both supplied Documents screenshots were inspected. Screenshot 1 shows 89.4 s, 2.29 m error, 0.49 m uncertainty, rounded 100% within 2 m and an innovation rejection. Its quality setting/seed are not visible. The visible zones are outside the replay route. Screenshot 2 is at **0 s**, quality **34%**, and displays **100%**, not the separately described 71.1%. Consequently the exact 89.4 s state and alleged 7 m gap cannot be uniquely reconstructed from these two files.

Controlled old-code runs reproduce the failure class, not that exact screenshot: at 89.4 s quality 20% gives 2.496 m error with 0.544 m uncertainty; quality 34% gives 0.474 m with 0.397 m. A legacy quality search did not find an exact screenshot match. Do not read metric distance from the aerial image: its registration is approximate. Current tests compare the dashboard error, frame Euclidean error and inverse-transformed map displacement at the same frame.

**A rejection cascade was confirmed for degraded GPS followed by clean fixes.** The old filter injected position noise without adding its known variance to measurement covariance, then became overconfident around a displaced estimate. Controlled 90 s restorations, with wheel-scale calibration, lever-arm change and recovery guard disabled to isolate this fix:

| Simulated quality | Old whole RMSE | Corrected noise covariance RMSE | Consecutive healthy rejections after restoration, old → corrected |
|---|---:|---:|---:|
| 0% | 4.201 m | 0.769 m | 108 → 0 |
| 20% | 1.943 m | 0.473 m | 126 → 0 |

Old fresh healthy rejection runs were 90.078864–100.783367 s and 90.078864–102.601719 s respectively. Missing candidates and simulated-degraded candidates are counted separately in GPS opportunity logs; they are not called healthy gate rejections.

Calibration exposed another failure: a sustained 10 m jump could eventually enter the NIS gate as covariance grew. With the discontinuity/recovery guard disabled, 87 faulty fixes were accepted, RMSE was 4.187 m, and restoration had 216 consecutive healthy rejections; recovery took 24.8 s. The final guard quarantines discontinuities and requires five fresh healthy fixes spanning 0.3–1.0 s, mutually consistent within 0.5 m and within 2 m of a trusted-state wheel+IMU continuation. The final jump run accepts **0/300** injected fixes, then intentionally waits four healthy fixes before accepting the fifth. Single teleports and stable distant clusters remain rejected. This is a conservative recovery mechanism, not universal relocalization; sufficiently large real drift or gradual GPS bias remains a limitation.

Each GPS opportunity records replay time, fault state, availability/health, mode/diagnostic age, innovation, S, R, NIS/threshold, reason, accepted/trusted age, controls/ages, prior/post covariance, guard state, and evaluation-only reference error. `tools/benchmark.py` saves JSONL logs for inspection.

## Final measured results

169.2 s replay after initialization; defaults unless an ablation is named:

| Run | Horizontal RMSE | Peak error |
|---|---:|---:|
| Recorded GPS, gated / ungated | 0.028 m | 0.156 m |
| Wheel+IMU / full outage after initialization | 0.870 m | 1.702 m |
| Wheel-only | 13.220 m | 30.995 m |
| Quality 34%, gated | 0.503 m | 1.663 m |
| 10 m jump, 30–60 s, gated | 0.240 m | 1.043 m |
| Same jump, ungated | 4.191 m | 10.179 m |

Before corrections, recorded RMSE was 0.045 m, quality-34% RMSE 1.706 m, and full-outage RMSE 3.404 m. Isolating wheel scale with lever-arm correction already enabled reduced full-outage RMSE 3.454 → 0.870 m. The measured development straight GPS/wheel speed ratio was about 0.890, versus 0.910 in turns; this is supporting evidence, not a held-out fitted calibration. Slip and gyro bias are not completely modeled.

All injected outage intervals had zero accepted GPS corrections while prediction continued. At 1 m tolerance, full outage stays within tolerance for 118.3/169.2 s; first sustained breach is 99.5 s and no recovery is reported because clean fixes never return. The jump's fault-window RMSE is 0.551 m, within tolerance 29.6/30 s, recovery 3.5 s; ungated is within tolerance only 0.1/30 s. Wheel+IMU fault-window RMSE is 0.430 m, better than gated in that particular window. Quality-34% ungated RMSE is also slightly better, 0.496 m. Gating is not uniformly superior.

Development outages start at 30 s; held-out intervals start at 90 s, both spanning straights and turns. Gated whole-replay RMSE for 10/30/60 s outages is 0.045/0.235/0.451 m in development and 0.086/0.224/0.383 m in the held-out intervals. These are **held-out intervals within one recording**, not independent-sequence validation. All tolerance, fault-window, peak, sustained-breach and recovery results are in the CSV. Recovery/breach times include the configured sustained dwell; they do not count a single crossing.

## Confidence and policy

Probability is computed for a centered 2-D Gaussian inside a metric-radius disk, retaining anisotropy; Monte Carlo regression tests verify it. Invalid covariance is explicit. Near-one displays `>99.9%`, never rounded `100.0%`. Operator measured error and covariance summary are separate; probability and coverage live in Diagnostics.

At 1 m, empirical coverage / mean model probability: nominal 100% / 99.9996%; degraded 34% quality 97.40% / 91.95%; full outage 69.94% / 5.57%; held-out 60 s fault 99% / 15.62%. The 95% model ellipse covered 100% nominal/full-outage samples and 99.17% degraded samples. **Outage uncertainty is very conservative and not empirically calibrated.** High nominal agreement is also influenced by the shared RTK source. Do not present these probabilities as validated safety guarantees.

Policy uses covariance summary and trusted-fix age, independently of evaluation tolerance: Slow at ≥1 m or ≥2 s; Stop at ≥3 m or ≥8 s, or invalid prediction inputs. Recommendations are 100% / 35% / 0%. Recovery takes 3 sustained seconds per downward step. Simulated-degraded acceptance does not reset trusted-fix age. Replay continues at Stop. Advisor is offline and cannot change these decisions.

## Recorded LiDAR trial

The local uncompressed base bag contains `/velodyne_points`, IMU, magnetometer, GPS and receiver diagnostics, spanning Unix 1689715608.9880624–1689716137.0324001. The odom bag contains wheel odometry and extends to 1689716895.921179. Inventory is reproducible with `tools/inventory_bag.py`.

`tools/lidar_baseline.py` implements planar scan-to-scan trimmed ICP at about 2 Hz with height/range/voxel filtering, wheel+IMU seeding, three initial lateral hypotheses, and overlap/residual/ambiguity/jump checks. The matching path uses no RTK reference and builds no evaluation map. Initial GPS pose is shared; wheel calibration is disabled in this experimental baseline. Evaluation interpolates the reference only afterward.

| Exact matched timestamps | LiDAR RMSE / peak | Raw wheel+IMU RMSE / peak | Calibrated wheel+IMU RMSE / peak |
|---|---:|---:|---:|
| Development 0–80 s, 159 samples | 1.662 / 2.652 m | 2.493 / 4.189 m | 0.461 / 0.828 m |
| Held-out 90–169.2 s, 156 samples | 5.665 / 8.971 m | 4.240 / 5.828 m | 1.156 / 1.625 m |

Match acceptance was 96.9% and 100% respectively: the quality gates failed to detect repetitive-orchard ambiguity. **LiDAR was not integrated as a trusted fallback because it worsened held-out performance.** The command in README reproduces this unsuccessful baseline; no claim of map localization is made.

## Desktop, import and automated verification

38 automated tests passed in 12.142 s with the real ZIP enabled. Coverage includes outage blocking, covariance/NIS mathematics, restoration ablations, persistent-jump/single-outlier guards, causal initialization, anisotropic probability, stale diagnostics/controls, reference gaps, policy crossings/recovery, background replay, failed-import preservation and stale-result handling.

The actual native desktop launched. A harness clicked Open ZIP with controlled chooser return paths and exercised real A → synthetic fixture B → real A. Sequence labels, origin, map selection and playback changed correctly. Bad imports preserved the session. Startup and resize at 1100×760 / 1500×950, recorded/outage/jump replay, play/pause, synchronized scrubbing and Stop at 45 s / Normal at 70 s passed. A saved window image was inspected. Map transform tests independently verify cover sizing, zoom and metric click inversion.

The first OS-native file-picker automation stalled; OS screen capture returned `could not create image from display`. The second harness used controlled dialog selections and reached a harness-only `QPoint - QPointF` error in the final canopy-click check. That arithmetic has been corrected, but the full GUI was not relaunched again. The displayed layout was checked before the final wheel-calibration/guard changes; those backend changes passed automated tests afterward.

Remaining manual checks: native OS chooser interaction; final interactive canopy click/pan and full corrected desktop harness with the latest backend; a second **real** CitrusFarm ZIP (none was available). The fixture regression is explicitly synthetic and is not evidence of a second real-data import. Run the README desktop verification command, then open an additional real ZIP and switch A → B → A.

## Image registration

The clean user-supplied image is registered through eight identifiable surviving tree-row landmarks to the original figure's metric registration. Five original held-out route turns have residuals 1.37, 4.75, 3.64, 1.83, 3.37 px; three clean held-out landmarks have residuals 1.72, 3.93, 6.44 px. The original figure contains a baked-in route; the main display uses the clean image. Generated details and approximate correspondence prevent a survey-grade claim. All metric errors are computed before image transformation. Only matching Sequence 01 uses this image; other recordings use Metric view.
